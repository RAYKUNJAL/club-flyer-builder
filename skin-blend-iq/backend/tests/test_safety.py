"""Safety controls (spec sections 3, 12, 19): lot blocking, mandatory
swatch verification, approval gates, synthetic-data treatment block,
consent requirements, and role permissions."""

import pytest

from .conftest import (
    calibrated_measurement,
    create_client_and_case,
    create_measured_kit,
    create_staff,
    locked_formula,
    register_studio,
)


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
    return calibrated_measurement(client, studio["headers"], case_bundle["case"]["id"])


def _generate(client, studio, kit_bundle, case_bundle, measurement, **over):
    payload = {
        "target_measurement_id": measurement["id"],
        "pigment_kit_id": kit_bundle["kit"]["id"],
        "case_id": case_bundle["case"]["id"],
        "total_drops": 20,
        "lot_selection": kit_bundle["lot_selection"],
    }
    payload.update(over)
    return client.post("/v1/formulas/generate", headers=studio["headers"], json=payload)


class TestLotBlocking:
    def test_recalled_lot_blocks_generation(self, client, studio, kit_bundle, case_bundle, measurement):
        lot_id = kit_bundle["lot_selection"]["P-R"]
        r = client.post(f"/v1/recalls?lot_id={lot_id}", headers=studio["headers"],
                        json={"reason": "manufacturer contamination notice"})
        assert r.status_code == 201, r.text
        recall = r.json()

        r = _generate(client, studio, kit_bundle, case_bundle, measurement)
        assert r.status_code == 409
        assert r.json()["detail"]["blocked"]["P-R"] == "recalled"

        # Restore with a fresh lot for later tests.
        r = client.post("/v1/pigment-lots", headers=studio["headers"], json={
            "product_id": kit_bundle["products"]["P-R"]["id"],
            "lot_number": "LOT-P-R-2", "expiry_date": "2027-12-31", "quantity_ml": 30.0,
        })
        kit_bundle["lot_selection"]["P-R"] = r.json()["id"]
        kit_bundle["recall"] = recall

    def test_expired_lot_blocked(self, client, studio, kit_bundle, case_bundle, measurement):
        r = client.post("/v1/pigment-lots", headers=studio["headers"], json={
            "product_id": kit_bundle["products"]["P-Y"]["id"],
            "lot_number": "LOT-P-Y-EXPIRED", "expiry_date": "2024-01-01", "quantity_ml": 30.0,
        })
        expired = r.json()["id"]
        selection = dict(kit_bundle["lot_selection"], **{"P-Y": expired})
        r = _generate(client, studio, kit_bundle, case_bundle, measurement, lot_selection=selection)
        assert r.status_code == 409
        assert r.json()["detail"]["blocked"]["P-Y"] == "expired"

    def test_quarantined_lot_blocked(self, client, studio, kit_bundle, case_bundle, measurement):
        lot_id = kit_bundle["lot_selection"]["P-B"]
        r = client.post(f"/v1/pigment-lots/{lot_id}/quarantine", headers=studio["headers"],
                        json={"reason": "suspect batch pending review"})
        assert r.status_code == 200
        r = _generate(client, studio, kit_bundle, case_bundle, measurement)
        assert r.status_code == 409
        assert r.json()["detail"]["blocked"]["P-B"] == "quarantined"
        # Replace for later tests.
        r = client.post("/v1/pigment-lots", headers=studio["headers"], json={
            "product_id": kit_bundle["products"]["P-B"]["id"],
            "lot_number": "LOT-P-B-2", "expiry_date": "2027-12-31", "quantity_ml": 30.0,
        })
        kit_bundle["lot_selection"]["P-B"] = r.json()["id"]

    def test_recall_finds_affected_clients(self, client, studio, kit_bundle):
        """A recall on a lot used in a locked formula identifies the client."""
        bundle = create_client_and_case(client, studio["headers"])
        m = calibrated_measurement(client, studio["headers"], bundle["case"]["id"])
        f = locked_formula(client, studio["headers"], kit_bundle, bundle["case"]["id"], m["id"])
        used_lot = next(i["lot_id"] for i in f["ingredients"] if i["drops"] > 0)
        r = client.post(f"/v1/recalls?lot_id={used_lot}", headers=studio["headers"],
                        json={"reason": "post-market recall"})
        assert r.status_code == 201
        r = client.get(f"/v1/recalls/{r.json()['id']}/affected-clients", headers=studio["headers"])
        assert r.status_code == 200
        affected = r.json()["affected_clients"]
        assert any(a["client_id"] == bundle["client"]["id"] for a in affected)
        # Replace the recalled lot so later tests keep a clean selection.
        code = next(i["code"] for i in f["ingredients"] if i["lot_id"] == used_lot)
        r = client.post("/v1/pigment-lots", headers=studio["headers"], json={
            "product_id": kit_bundle["products"][code]["id"],
            "lot_number": f"LOT-{code}-3", "expiry_date": "2027-12-31", "quantity_ml": 30.0,
        })
        kit_bundle["lot_selection"][code] = r.json()["id"]

    def test_lock_reverifies_lots(self, client, studio, kit_bundle):
        """A recall landing after approval must block locking."""
        bundle = create_client_and_case(client, studio["headers"])
        m = calibrated_measurement(client, studio["headers"], bundle["case"]["id"])
        r = _generate(client, studio, kit_bundle, bundle, m)
        assert r.status_code == 201, r.text
        f = r.json()
        r = client.post("/v1/swatches", headers=studio["headers"], json={"formula_id": f["id"]})
        sw = r.json()
        client.post(f"/v1/swatches/{sw['id']}/measure", headers=studio["headers"],
                    json={"lab": f["predicted_lab"], "source_type": "instrument"})
        r = client.post(f"/v1/formulas/{f['id']}/approve", headers=studio["headers"])
        assert r.status_code == 200
        used_lot = next(i["lot_id"] for i in f["ingredients"] if i["drops"] > 0)
        code = next(i["code"] for i in f["ingredients"] if i["lot_id"] == used_lot)
        client.post(f"/v1/pigment-lots/{used_lot}/quarantine", headers=studio["headers"],
                    json={"reason": "late quarantine"})
        r = client.post(f"/v1/formulas/{f['id']}/lock", headers=studio["headers"])
        assert r.status_code == 409
        # Clean up: fresh lot for subsequent tests.
        r = client.post("/v1/pigment-lots", headers=studio["headers"], json={
            "product_id": kit_bundle["products"][code]["id"],
            "lot_number": f"LOT-{code}-4", "expiry_date": "2027-12-31", "quantity_ml": 30.0,
        })
        kit_bundle["lot_selection"][code] = r.json()["id"]


class TestWorkflowGates:
    def test_approve_requires_swatch(self, client, studio, kit_bundle, case_bundle, measurement):
        r = _generate(client, studio, kit_bundle, case_bundle, measurement)
        assert r.status_code == 201, r.text
        f = r.json()
        r = client.post(f"/v1/formulas/{f['id']}/approve", headers=studio["headers"])
        assert r.status_code == 409
        assert "swatch" in r.json()["detail"].lower()
        # Prepared but unmeasured swatch still blocks approval.
        r = client.post("/v1/swatches", headers=studio["headers"], json={"formula_id": f["id"]})
        assert r.status_code == 201
        r = client.post(f"/v1/formulas/{f['id']}/approve", headers=studio["headers"])
        assert r.status_code == 409

    def test_lock_requires_approval(self, client, studio, kit_bundle, case_bundle, measurement):
        r = _generate(client, studio, kit_bundle, case_bundle, measurement)
        f = r.json()
        r = client.post(f"/v1/formulas/{f['id']}/lock", headers=studio["headers"])
        assert r.status_code == 409

    def test_treatment_requires_locked_formula(self, client, studio, kit_bundle, case_bundle, measurement):
        r = _generate(client, studio, kit_bundle, case_bundle, measurement)
        f = r.json()
        r = client.post("/v1/treatment-sessions", headers=studio["headers"], json={
            "case_id": case_bundle["case"]["id"], "formula_id": f["id"],
        })
        assert r.status_code == 409

    def test_negative_drops_rejected(self, client, studio, kit_bundle, case_bundle, measurement):
        r = _generate(client, studio, kit_bundle, case_bundle, measurement)
        f = r.json()
        bad = dict(f["recipe"])
        bad[next(iter(bad))] = -1
        r = client.post(f"/v1/formulas/{f['id']}/adjust", headers=studio["headers"],
                        json={"drops": bad, "reason": "invalid"})
        assert r.status_code == 422

    def test_trainee_cannot_approve(self, client, studio, kit_bundle, case_bundle, measurement):
        trainee = create_staff(client, studio["headers"], "trainee")
        client.post("/v1/auth/acknowledge", headers=trainee["headers"])
        r = _generate(client, studio, kit_bundle, case_bundle, measurement)
        f = r.json()
        r = client.post("/v1/swatches", headers=studio["headers"], json={"formula_id": f["id"]})
        sw = r.json()
        client.post(f"/v1/swatches/{sw['id']}/measure", headers=studio["headers"],
                    json={"lab": f["predicted_lab"], "source_type": "instrument"})
        r = client.post(f"/v1/formulas/{f['id']}/approve", headers=trainee["headers"])
        assert r.status_code == 403

    def test_approval_requires_professional_ack(self, client, studio, kit_bundle, case_bundle, measurement):
        artist = create_staff(client, studio["headers"], "artist")  # no acknowledge call
        r = _generate(client, studio, kit_bundle, case_bundle, measurement)
        f = r.json()
        r = client.post("/v1/swatches", headers=studio["headers"], json={"formula_id": f["id"]})
        sw = r.json()
        client.post(f"/v1/swatches/{sw['id']}/measure", headers=studio["headers"],
                    json={"lab": f["predicted_lab"], "source_type": "instrument"})
        r = client.post(f"/v1/formulas/{f['id']}/approve", headers=artist["headers"])
        assert r.status_code == 403
        assert "acknowledgment" in r.json()["detail"].lower()

    def test_quarantine_requires_senior_role(self, client, studio, kit_bundle):
        artist = create_staff(client, studio["headers"], "artist")
        lot_id = kit_bundle["lot_selection"]["P-K"]
        r = client.post(f"/v1/pigment-lots/{lot_id}/quarantine", headers=artist["headers"],
                        json={"reason": "should be denied"})
        assert r.status_code == 403


class TestSyntheticDataBlock:
    """Appendix B warning 1: prototype/synthetic recipes must never be
    used on a person — enforced at the treatment endpoints."""

    def test_synthetic_kit_formula_blocked_from_treatment(self, client, studio, case_bundle, measurement):
        # The seeded demo studio's synthetic kit is per-tenant; build one here.
        r = client.post("/v1/pigment-products", headers=studio["headers"], json={
            "manufacturer": "Demo", "product_name": "Synth Y",
            "internal_code": "S-Y", "color_role": "primary_yellow",
        })
        py = r.json()
        r = client.post("/v1/pigment-lots", headers=studio["headers"], json={
            "product_id": py["id"], "lot_number": "S-1", "expiry_date": "2027-12-31",
        })
        lot = r.json()
        r = client.post("/v1/pigment-kits", headers=studio["headers"], json={
            "name": "Synthetic kit", "dataset_version": "synthetic-1",
            "data_source": "synthetic",
            "pigments": [{"product_id": py["id"], "code": "S-Y"}],
        })
        kit = r.json()
        client.post(f"/v1/pigment-kits/{kit['id']}/mixture-samples", headers=studio["headers"],
                    json={"ratios": {"S-Y": 1.0}, "lab": [85.0, 5.0, 78.0], "source": "synthetic"})

        r = client.post("/v1/formulas/generate", headers=studio["headers"], json={
            "target_measurement_id": measurement["id"],
            "pigment_kit_id": kit["id"],
            "case_id": case_bundle["case"]["id"],
            "total_drops": 20,
            "lot_selection": {"S-Y": lot["id"]},
        })
        assert r.status_code == 201
        f = r.json()
        assert f["treatment_grade"] is False
        assert any("PROTOTYPE" in w for w in f["warnings"])

        # Walk it to locked, then confirm treatment endpoints refuse it.
        r = client.post("/v1/swatches", headers=studio["headers"], json={"formula_id": f["id"]})
        sw = r.json()
        client.post(f"/v1/swatches/{sw['id']}/measure", headers=studio["headers"],
                    json={"lab": f["predicted_lab"], "source_type": "instrument"})
        client.post(f"/v1/formulas/{f['id']}/approve", headers=studio["headers"])
        r = client.post(f"/v1/formulas/{f['id']}/lock", headers=studio["headers"])
        assert r.status_code == 200

        for endpoint, payload in [
            ("/v1/test-spots", {"case_id": case_bundle["case"]["id"], "formula_id": f["id"]}),
            ("/v1/treatment-sessions", {"case_id": case_bundle["case"]["id"], "formula_id": f["id"]}),
        ]:
            r = client.post(endpoint, headers=studio["headers"], json=payload)
            assert r.status_code == 403, f"{endpoint} must safety-block synthetic formulas"
            assert "SAFETY BLOCK" in r.json()["detail"]

    def test_non_treatment_grade_target_blocked(self, client, studio, kit_bundle, case_bundle):
        """Manual (quick) measurement -> formula never treatment-grade."""
        r = client.post("/v1/measurements/manual", headers=studio["headers"],
                        json={"lab": [59.0, 13.0, 20.0], "source_type": "manual"})
        m = r.json()
        r = client.post("/v1/formulas/generate", headers=studio["headers"], json={
            "target_measurement_id": m["id"],
            "pigment_kit_id": kit_bundle["kit"]["id"],
            "case_id": case_bundle["case"]["id"],
            "total_drops": 20,
            "lot_selection": kit_bundle["lot_selection"],
        })
        assert r.status_code == 201
        assert r.json()["treatment_grade"] is False


class TestConsent:
    def test_treatment_requires_consent(self, client, studio, kit_bundle):
        bundle = create_client_and_case(client, studio["headers"], consents=())
        m = calibrated_measurement(client, studio["headers"], bundle["case"]["id"])
        f = locked_formula(client, studio["headers"], kit_bundle, bundle["case"]["id"], m["id"])
        r = client.post("/v1/test-spots", headers=studio["headers"], json={
            "case_id": bundle["case"]["id"], "formula_id": f["id"],
        })
        assert r.status_code == 409
        assert "consent" in r.json()["detail"].lower()

    def test_consent_kinds_are_separate(self, client, studio):
        bundle = create_client_and_case(client, studio["headers"], consents=("marketing",))
        r = client.get(f"/v1/clients/{bundle['client']['id']}", headers=studio["headers"])
        kinds = {c["kind"]: c["granted"] for c in r.json()["consents"]}
        assert kinds == {"marketing": True}
