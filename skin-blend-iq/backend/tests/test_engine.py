"""Formula engine validation: quantization exactness, scaling volume
preservation, correction fitting, quality scoring, and the section 21
proof-of-concept assertions."""

import numpy as np
import pytest

from app.colorscience import delta_e_2000, lab_to_srgb, srgb_to_lab
from app.colorscience.correction import apply_correction, fit_correction
from app.colorscience.quality import score_image
from app.formula.mixtures import synthetic_demo_kit
from app.formula.quantize import drops_to_ratios, quantization_error, quantize_drops
from app.formula.scaling import (
    ML_PER_US_FL_OZ,
    coverage_estimate_ml,
    drops_to_ml,
    scale_to_volume,
)
from app.formula.solver import solve

POC_TARGETS = {
    "demo_light_warm": (76.0, 12.0, 24.0),
    "demo_medium_neutral": (59.0, 13.0, 20.0),
    "demo_deep_warm": (38.0, 17.0, 18.0),
    "demo_deep_cool": (31.0, 12.0, 7.0),
}


class TestQuantization:
    @pytest.mark.parametrize("total", [10, 20, 40, 7, 33, 100])
    def test_exact_totals(self, total):
        ratios = {"P-Y": 0.31, "P-R": 0.11, "P-B": 0.052, "P-W": 0.278, "P-K": 0.25}
        drops = quantize_drops(ratios, total)
        assert sum(drops.values()) == total
        assert all(v >= 0 for v in drops.values())

    def test_deterministic(self):
        ratios = {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
        assert quantize_drops(ratios, 20) == quantize_drops(ratios, 20)

    def test_largest_remainder_property(self):
        drops = quantize_drops({"A": 0.5, "B": 0.5}, 21)
        assert sum(drops.values()) == 21
        assert sorted(drops.values()) == [10, 11]

    def test_unnormalized_input(self):
        drops = quantize_drops({"A": 2.0, "B": 6.0}, 20)
        assert drops == {"A": 5, "B": 15}

    def test_quantization_error_reported(self):
        ratios = {"A": 0.33, "B": 0.67}
        drops = quantize_drops(ratios, 10)
        err = quantization_error(ratios, drops)
        assert set(err) == {"A", "B"}
        assert abs(sum(err.values())) < 1e-9

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            quantize_drops({"A": 1.0}, 0)
        with pytest.raises(ValueError):
            quantize_drops({"A": 0.0}, 10)
        with pytest.raises(ValueError):
            drops_to_ratios({"A": 0})


class TestScaling:
    @pytest.mark.parametrize("preset_ml", [
        ML_PER_US_FL_OZ / 8, ML_PER_US_FL_OZ / 4, ML_PER_US_FL_OZ / 2,
        ML_PER_US_FL_OZ, ML_PER_US_FL_OZ * 2, ML_PER_US_FL_OZ * 4,
    ])
    def test_exact_total_volume(self, preset_ml):
        ratios = {"Yellow": 0.30, "Red": 0.10, "Olive": 0.05, "Brown": 0.30, "White": 0.25}
        out = scale_to_volume(ratios, preset_ml)
        assert sum(out["ingredients_ml"].values()) == pytest.approx(out["total_ml"], abs=1e-9)
        assert out["total_ml"] == pytest.approx(preset_ml, abs=1e-4)

    def test_spec_example_half_ounce(self):
        # Expansion spec example: 1/2 oz of 30/10/5/30/25.
        out = scale_to_volume(
            {"Yellow": 0.30, "Red": 0.10, "Olive": 0.05, "Brown": 0.30, "White": 0.25},
            ML_PER_US_FL_OZ / 2,
        )
        assert out["ingredients_ml"]["Yellow"] == pytest.approx(4.4360, abs=0.001)
        assert out["ingredients_ml"]["Red"] == pytest.approx(1.4787, abs=0.001)
        assert out["ingredients_ml"]["Olive"] == pytest.approx(0.7393, abs=0.001)
        assert out["ingredients_ml"]["White"] == pytest.approx(3.6967, abs=0.001)

    def test_rounding_differences_disclosed(self):
        out = scale_to_volume({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}, 10.0)
        assert "rounding_differences_ml" in out
        assert sum(out["ingredients_ml"].values()) == pytest.approx(10.0, abs=1e-9)

    def test_drops_to_ml(self):
        out = drops_to_ml({"A": 10, "B": 10}, drop_volume_ml=0.05)
        assert out["total_ml"] == pytest.approx(1.0)
        out = drops_to_ml({"A": 10, "B": 10}, drop_volume_ml=0.05,
                          per_pigment_drop_volume={"A": 0.06})
        assert out["ingredients_ml"]["A"] == pytest.approx(0.6)

    def test_coverage_estimate(self):
        ml = coverage_estimate_ml(25.0, 0.02, passes=2, texture_factor=1.1, reserve_factor=1.2)
        assert ml == pytest.approx(25.0 * 0.02 * 2 * 1.1 * 1.2)
        with pytest.raises(ValueError):
            coverage_estimate_ml(-1, 0.02)


class TestPoCFramework:
    """Section 21 proof-of-concept: software-flow validation on the
    synthetic kit. Never a source of human-use recipes."""

    @pytest.fixture(scope="class")
    def kit(self):
        return synthetic_demo_kit()

    @pytest.mark.parametrize("name", list(POC_TARGETS))
    @pytest.mark.parametrize("total", [20, 40])
    def test_recipes_exact_and_nonnegative(self, kit, name, total):
        result = solve(kit, POC_TARGETS[name], total_drops=total)
        for cand in result["candidates"]:
            assert sum(cand.drops.values()) == total
            assert all(v >= 0 for v in cand.drops.values())

    @pytest.mark.parametrize("name", list(POC_TARGETS))
    def test_color_recalculated_after_rounding(self, kit, name):
        result = solve(kit, POC_TARGETS[name], total_drops=20)
        best = result["candidates"][0]
        # Predicted color must come from the quantized recipe, not the
        # continuous ratios.
        recomputed = kit.predict_lab(drops_to_ratios(best.drops))
        # (stored predicted_lab is rounded to 3 decimals)
        assert delta_e_2000(recomputed, best.predicted_lab) < 0.01
        assert best.rounding_delta_e == pytest.approx(
            best.delta_e_2000 - best.delta_e_2000_continuous, abs=1e-3
        )

    @pytest.mark.parametrize("name", list(POC_TARGETS))
    def test_finer_quantization_reduces_error(self, kit, name):
        de20 = solve(kit, POC_TARGETS[name], total_drops=20)["candidates"][0].delta_e_2000
        de40 = solve(kit, POC_TARGETS[name], total_drops=40)["candidates"][0].delta_e_2000
        assert de40 <= de20 + 0.25  # finer caps must not be meaningfully worse

    def test_all_four_target_classes_processed(self, kit):
        results = {n: solve(kit, t, total_drops=20) for n, t in POC_TARGETS.items()}
        assert len(results) == 4
        for r in results.values():
            assert r["candidates"]

    def test_deterministic_solver(self, kit):
        a = solve(kit, POC_TARGETS["demo_medium_neutral"], total_drops=20)
        b = solve(kit, POC_TARGETS["demo_medium_neutral"], total_drops=20)
        assert a["candidates"][0].drops == b["candidates"][0].drops

    def test_constraints_respected(self, kit):
        result = solve(kit, POC_TARGETS["demo_medium_neutral"], total_drops=20,
                       excluded=["P-B"], max_pigments=3)
        best = result["candidates"][0]
        assert best.drops.get("P-B", 0) == 0
        assert sum(1 for v in best.drops.values() if v > 0) <= 3

    def test_out_of_gamut_flagged(self, kit):
        # Saturated green is far outside any skin-tone pigment gamut.
        result = solve(kit, (60.0, -70.0, 60.0), total_drops=20)
        assert result["gamut_status"] == "outside"
        assert result["warnings"]


class TestCorrectionAndQuality:
    def test_correction_recovers_cast(self):
        # Channel cast applied to known colors must be invertible.
        reference_lab = [[95, 0, 0], [70, 0, 0], [40, 0, 0], [10, 0, 0], [70, 15, 20], [40, 18, 22]]
        cast = np.array([0.9, 1.0, 0.85])
        observed = [list(np.array(lab_to_srgb(tuple(lab))) * cast) for lab in reference_lab]
        fit = fit_correction(observed, reference_lab)
        assert fit["passed"], fit
        assert fit["residual_delta_e00"] < 1.0
        # Applying the correction to a distorted unseen color recovers it.
        true_rgb = lab_to_srgb((59.0, 13.0, 20.0))
        distorted = list(np.array(true_rgb) * cast)
        corrected = apply_correction(distorted, fit["matrix"])
        assert delta_e_2000(srgb_to_lab(tuple(corrected)), (59.0, 13.0, 20.0)) < 1.0

    def test_correction_needs_enough_patches(self):
        with pytest.raises(ValueError):
            fit_correction([[100, 100, 100]] * 3, [[50, 0, 0]] * 3)

    def test_quality_scoring_flags_bad_images(self):
        from io import BytesIO

        from PIL import Image

        rng = np.random.default_rng(7)
        # Sharp, well-exposed, noisy image -> pass.
        good = np.clip(rng.normal(140, 20, (600, 800, 3)), 0, 253).astype(np.uint8)
        buf = BytesIO(); Image.fromarray(good).save(buf, "PNG")
        q = score_image(buf.getvalue())
        assert q["grade"] == "pass", q

        # Flat blurred image -> focus failure.
        flat = np.full((600, 800, 3), 140, dtype=np.uint8)
        buf = BytesIO(); Image.fromarray(flat).save(buf, "PNG")
        q = score_image(buf.getvalue())
        assert "focus" in q["failures"]

        # Heavily clipped image -> overexposure failure.
        over = good.copy(); over[:300] = 255
        buf = BytesIO(); Image.fromarray(over).save(buf, "PNG")
        q = score_image(buf.getvalue())
        assert "overexposure" in q["failures"]
        assert q["grade"] == "fail"

        # Tiny image -> resolution failure.
        small = np.clip(rng.normal(140, 20, (100, 100, 3)), 0, 253).astype(np.uint8)
        buf = BytesIO(); Image.fromarray(small).save(buf, "PNG")
        q = score_image(buf.getvalue())
        assert "resolution" in q["failures"]
