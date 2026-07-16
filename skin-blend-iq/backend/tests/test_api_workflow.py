"""End-to-end workflow (spec section 5): client -> consent -> capture ->
analyze -> formula -> quantize -> swatch -> approve -> lock -> batch ->
test spot -> treatment -> follow-up -> report."""

import pytest

from app.colorscience import delta_e_2000

from .conftest import (
    calibrated_measurement,
    create_client_and_case,
    create_measured_kit,
    create_staff,
    locked_formula,
    make_capture_image,
    register_studio,
)

TRUE_SKIN_LAB = (59.0, 13.0, 20.0)


@pytest.fixture(scope="module")
def studio(client):
    return register_studio(client)


@pytest.fixture(scope="module")
def kit_bundle(client, studio):
    return create_measured_kit(client, studio["headers"])


@pytest.fixture(scope="module")
def case_bundle(client, studio):
    return create_client_and_case(client, studio["headers"])


@pytest.fixture(scope="module")
def measurement(client, studio, case_bundle):
    return calibrated_measurement(
        client, studio["headers"], case_bundle["case"]["id"], skin_lab=TRUE_SKIN_LAB
    )


class TestCalibratedCapture:
    def test_measurement_is_treatment_grade(self, measurement):
        assert measurement["treatment_grade"] is True, measurement

    def test_measurement_recovers_true_color(self, measurement):
        got = (measurement["lab_l"], measurement["lab_a"], measurement["lab_b"])
        assert delta_e_2000(got, TRUE_SKIN_LAB) < 2.0, got

    def test_descriptors_present(self, measurement):
        assert measurement["illuminant"] == "D65"
        assert measurement["observer"] == "2deg"
        assert measurement["undertone"] is not None
        assert measurement["ita_degrees"] is not None
        assert measurement["hsv"] is not None
        assert measurement["rgb_display"] is not None
        assert measurement["delta_e_uncertainty"] is not None

    def test_quick_capture_not_treatment_grade(self, client, studio, case_bundle):
        r = client.post("/v1/measurements/manual", headers=studio["headers"], json={
            "lab": [59.0, 13.0, 20.0], "source_type": "manual",
        })
        assert r.status_code == 201
        assert r.json()["treatment_grade"] is False

    def test_failed_quality_image_graded(self, client, studio, case_bundle):
        import numpy as np
        from io import BytesIO
        from PIL import Image

        cards = client.get("/v1/reference-cards", headers=studio["headers"]).json()
        r = client.post("/v1/captures", headers=studio["headers"], json={
            "case_id": case_bundle["case"]["id"], "mode": "calibrated",
            "reference_card_id": cards[0]["id"],
        })
        capture_id = r.json()["id"]
        flat = np.full((600, 800, 3), 140, dtype=np.uint8)  # blurred/flat
        buf = BytesIO(); Image.fromarray(flat).save(buf, "PNG")
        r = client.post(f"/v1/captures/{capture_id}/images", headers=studio["headers"],
                        files={"file": ("bad.png", buf.getvalue(), "image/png")})
        assert r.status_code == 201
        assert r.json()["grade"] == "fail"


class TestFormulaLifecycle:
    @pytest.fixture(scope="class")
    def formula(self, client, studio, kit_bundle, case_bundle, measurement):
        r = client.post("/v1/formulas/generate", headers=studio["headers"], json={
            "target_measurement_id": measurement["id"],
            "pigment_kit_id": kit_bundle["kit"]["id"],
            "case_id": case_bundle["case"]["id"],
            "total_drops": 20,
            "lot_selection": kit_bundle["lot_selection"],
        })
        assert r.status_code == 201, r.text
        return r.json()

    def test_generate_output_contract(self, formula):
        assert sum(formula["recipe"].values()) == 20
        assert all(v >= 0 for v in formula["recipe"].values())
        assert formula["status"] == "draft"
        assert formula["treatment_grade"] is True
        assert formula["model_version"] == "formula-engine-1.0.0"
        assert formula["dataset_version"] == "kit-test-2026-001"
        assert formula["gamut_status"] in ("inside", "outside")
        assert formula["predicted_delta_e00"] is not None
        assert formula["confidence"] is not None
        assert formula["required_verification"] == "external_swatch"
        assert formula["alternatives"]
        assert formula["continuous_ratios"]  # master ratio preserved
        for ing in formula["ingredients"]:
            assert ing["lot_number"] and ing["expiry_date"]

    def test_requantize_to_40(self, client, studio, formula):
        r = client.post(f"/v1/formulas/{formula['id']}/quantize",
                        headers=studio["headers"], json={"total_drops": 40})
        assert r.status_code == 200, r.text
        out = r.json()
        assert sum(out["recipe"].values()) == 40
        assert out["rounding_delta_e"] is not None

    def test_adjust_records_reason_and_resets_swatch(self, client, studio, formula):
        r = client.get(f"/v1/formulas/{formula['id']}", headers=studio["headers"])
        recipe = r.json()["recipe"]
        code = max(recipe, key=recipe.get)
        recipe[code] += 1
        r = client.post(f"/v1/formulas/{formula['id']}/adjust", headers=studio["headers"],
                        json={"drops": recipe, "reason": "healed too cool last time"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["status"] == "artist_adjusted"
        r = client.get(f"/v1/formulas/{formula['id']}", headers=studio["headers"])
        assert len(r.json()["adjustments"]) == 1
        assert r.json()["adjustments"][0]["reason"] == "healed too cool last time"

    def test_swatch_approve_lock(self, client, studio, formula):
        r = client.post("/v1/swatches", headers=studio["headers"],
                        json={"formula_id": formula["id"]})
        assert r.status_code == 201
        swatch = r.json()
        r = client.get(f"/v1/formulas/{formula['id']}", headers=studio["headers"])
        pred = r.json()["predicted_lab"]
        r = client.post(f"/v1/swatches/{swatch['id']}/measure", headers=studio["headers"],
                        json={"lab": pred, "source_type": "instrument"})
        assert r.status_code == 200
        assert r.json()["delta_e00_vs_target"] is not None
        r = client.post(f"/v1/formulas/{formula['id']}/approve", headers=studio["headers"])
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        r = client.post(f"/v1/formulas/{formula['id']}/lock", headers=studio["headers"])
        assert r.status_code == 200
        out = r.json()
        assert out["status"] == "locked"
        assert out["locked_at"] is not None

    def test_locked_formula_is_immutable(self, client, studio, formula):
        r = client.get(f"/v1/formulas/{formula['id']}", headers=studio["headers"])
        recipe = r.json()["recipe"]
        r = client.post(f"/v1/formulas/{formula['id']}/adjust", headers=studio["headers"],
                        json={"drops": recipe, "reason": "should be refused"})
        assert r.status_code == 409
        r = client.post(f"/v1/formulas/{formula['id']}/quantize", headers=studio["headers"],
                        json={"total_drops": 10})
        assert r.status_code == 409

    def test_new_version_from_locked(self, client, studio, formula):
        r = client.post(f"/v1/formulas/{formula['id']}/new-version", headers=studio["headers"])
        assert r.status_code == 201
        out = r.json()
        assert out["version"] == 2
        assert out["status"] == "draft"
        assert out["parent_formula_id"] == formula["id"]


class TestBatchAndTreatment:
    @pytest.fixture(scope="class")
    def flow(self, client, studio, kit_bundle):
        bundle = create_client_and_case(client, studio["headers"])
        m = calibrated_measurement(client, studio["headers"], bundle["case"]["id"])
        f = locked_formula(client, studio["headers"], kit_bundle, bundle["case"]["id"], m["id"])
        return {"case": bundle["case"], "client": bundle["client"], "formula": f, "measurement": m}

    def test_scale_and_batch(self, client, studio, flow):
        f = flow["formula"]
        r = client.post(f"/v1/formulas/{f['id']}/scale", headers=studio["headers"],
                        json={"preset": "1/2_fl_oz"})
        assert r.status_code == 200
        scaled = r.json()
        assert scaled["total_ml"] == pytest.approx(14.7868, abs=0.001)
        assert sum(scaled["ingredients_ml"].values()) == pytest.approx(scaled["total_ml"], abs=1e-6)

        r = client.post("/v1/batches", headers=studio["headers"], json={
            "formula_id": f["id"], "preset": "1/4_fl_oz", "planned_zones": ["V01", "V02"],
        })
        assert r.status_code == 201, r.text
        batch = r.json()
        assert batch["display_code"].startswith("SBI-B-")
        assert "SKIN BLEND IQ" in batch["label_text"]
        assert "never return mixed pigment" in batch["label_text"]
        flow["batch"] = batch

        # Inventory was deducted.
        lots = client.get("/v1/pigment-lots", headers=studio["headers"]).json()
        used_lots = {i["lot_id"] for i in f["ingredients"] if i["drops"] > 0}
        for lot in lots:
            if lot["id"] in used_lots:
                assert lot["quantity_ml"] < 30.0

    def test_test_spot_gates_full_session(self, client, studio, flow):
        f = flow["formula"]
        case_id = flow["case"]["id"]
        # Full session before an approved test spot -> blocked.
        r = client.post("/v1/treatment-sessions", headers=studio["headers"], json={
            "case_id": case_id, "formula_id": f["id"],
        })
        assert r.status_code == 409
        assert "test spot" in r.json()["detail"].lower()

        r = client.post("/v1/test-spots", headers=studio["headers"], json={
            "case_id": case_id, "formula_id": f["id"], "location_note": "behind ear",
            "size_mm": 5, "follow_up_due": "2026-08-30",
        })
        assert r.status_code == 201, r.text
        spot = r.json()
        r = client.post(f"/v1/test-spots/{spot['id']}/review", headers=studio["headers"], json={
            "healed_review": {"healed": True, "too_warm": False, "reaction": False},
            "approved": True,
        })
        assert r.status_code == 200
        assert r.json()["approved"] is True

        r = client.post("/v1/treatment-sessions", headers=studio["headers"], json={
            "case_id": case_id, "formula_id": f["id"],
            "batch_id": flow["batch"]["id"], "zones": ["V01"],
            "checklist": {"identity_verified": True, "consent_current": True},
        })
        assert r.status_code == 201, r.text
        flow["session"] = r.json()

        r = client.get(f"/v1/formulas/{f['id']}", headers=studio["headers"])
        assert r.json()["status"] == "used"

    def test_follow_up_and_senior_review(self, client, studio, flow):
        r = client.post("/v1/follow-ups", headers=studio["headers"], json={
            "session_id": flow["session"]["id"], "interval_days": 42,
            "review": {"healed": True, "too_light": False}, "outcome": "good_match",
        })
        assert r.status_code == 201, r.text
        fu = r.json()
        # Senior review; client has no ai_training consent -> stays private.
        r = client.post(f"/v1/follow-ups/{fu['id']}/review", headers=studio["headers"], json={
            "eligible_for_learning": True, "outcome": "good_match",
        })
        assert r.status_code == 200, r.text
        assert r.json()["eligible_for_learning"] is False
        assert "consent" in r.json().get("note", "").lower()

        r = client.get(f"/v1/formulas/{flow['formula']['id']}", headers=studio["headers"])
        assert r.json()["status"] == "outcome_reviewed"

    def test_pdf_report(self, client, studio, flow):
        r = client.get(f"/v1/formulas/{flow['formula']['id']}/report.pdf",
                       headers=studio["headers"])
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 800

    def test_batch_usage_tracking(self, client, studio, flow):
        b = flow["batch"]
        r = client.post(f"/v1/batches/{b['id']}/usage", headers=studio["headers"], json={
            "quantity_used_ml": 5.0, "quantity_discarded_ml": 2.0,
        })
        assert r.status_code == 200
        r = client.post(f"/v1/batches/{b['id']}/usage", headers=studio["headers"], json={
            "quantity_used_ml": 100.0, "quantity_discarded_ml": 0.0,
        })
        assert r.status_code == 422  # cannot exceed prepared quantity


class TestSupportingEndpoints:
    def test_dashboard(self, client, studio):
        r = client.get("/v1/dashboard", headers=studio["headers"])
        assert r.status_code == 200
        assert r.json()["clients"] >= 1

    def test_pricing_estimate(self, client, studio):
        r = client.post("/v1/pricing/estimate", headers=studio["headers"], json={
            "consultation_fee": 100, "test_spot_fee": 150, "minimum_fee": 200,
            "area_sq_in": 6.1, "area_rate_per_sq_in": 80, "complexity_factor": 1.2,
            "hours": 2, "hourly_rate": 150, "supplies": 40,
        })
        assert r.status_code == 200
        out = r.json()
        assert out["area_tier"] == "medium"
        assert out["estimate"] == pytest.approx(100 + 150 + 6.1 * 80 * 1.2 + 300 + 40, abs=0.01)

    def test_coverage_estimate(self, client, studio):
        r = client.post("/v1/coverage/estimate", headers=studio["headers"], json={
            "area_sq_cm": 25, "ml_per_sq_cm": 0.02, "passes": 2,
        })
        assert r.status_code == 200
        assert r.json()["estimated_ml"] > 0

    def test_body_zones(self, client, studio):
        bundle = create_client_and_case(client, studio["headers"])
        r = client.post(f"/v1/cases/{bundle['case']['id']}/zones", headers=studio["headers"],
                        json={"code": "V01", "label": "right shoulder", "area_sq_cm": 24.5})
        assert r.status_code == 201
        zone = r.json()
        r = client.post(f"/v1/zones/{zone['id']}/status", headers=studio["headers"],
                        json={"status": "do_not_treat", "notes": "active irritation"})
        assert r.status_code == 200
        assert r.json()["status"] == "do_not_treat"

    def test_dropper_calibration_warning(self, client, studio):
        r = client.post("/v1/dropper-calibrations", headers=studio["headers"], json={
            "drop_volume_ml_mean": 0.05, "drop_volume_ml_std": 0.002, "sample_count": 20,
        })
        assert r.status_code == 201
        assert r.json()["within_tolerance"] is True
        r = client.post("/v1/dropper-calibrations", headers=studio["headers"], json={
            "drop_volume_ml_mean": 0.05, "drop_volume_ml_std": 0.02, "sample_count": 20,
        })
        assert r.status_code == 201
        assert r.json()["within_tolerance"] is False
        assert "warning" in r.json()
