"""/v1/dashboard/flow returns factual chart data: pipeline counts and the
weekly inventory footprint must reconcile with the underlying records."""

import pytest

from .conftest import (
    calibrated_measurement,
    create_client_and_case,
    create_measured_kit,
    locked_formula,
    register_studio,
)


@pytest.fixture(scope="module")
def studio(client):
    return register_studio(client)


@pytest.fixture(scope="module")
def populated(client, studio):
    kit_bundle = create_measured_kit(client, studio["headers"])  # 5 lots x 30 mL received
    bundle = create_client_and_case(client, studio["headers"])
    m = calibrated_measurement(client, studio["headers"], bundle["case"]["id"])
    f = locked_formula(client, studio["headers"], kit_bundle, bundle["case"]["id"], m["id"])
    r = client.post("/v1/batches", headers=studio["headers"], json={
        "formula_id": f["id"], "preset": "1/4_fl_oz",
    })
    assert r.status_code == 201, r.text
    return {"kit": kit_bundle, "formula": f, "batch": r.json(), "case": bundle["case"]}


def test_pipeline_counts_are_factual(client, studio, populated):
    r = client.get("/v1/dashboard/flow", headers=studio["headers"])
    assert r.status_code == 200
    stages = {p["stage"]: p["count"] for p in r.json()["pipeline"]}
    assert stages["clients"] == 1
    assert stages["cases"] == 1
    assert stages["captures"] == 1
    assert stages["formulas"] == 1
    assert stages["swatch_verified"] == 1
    assert stages["locked"] == 1
    assert stages["sessions"] == 0  # no treatment session recorded yet
    assert stages["analyses"] >= 1


def test_footprint_reconciles_with_inventory(client, studio, populated):
    r = client.get("/v1/dashboard/flow", headers=studio["headers"])
    fp = r.json()["inventory_footprint"]
    assert len(fp["weeks"]) == 8
    rows = {row["code"]: row for row in fp["rows"]}
    batch_ml = populated["batch"]["ingredients_ml"]

    # Every product with recipe drops was received (30 mL) and consumed by
    # the batch; totals must match the batch's exact per-ingredient volumes.
    for code, ml in batch_ml.items():
        assert code in rows, f"{code} missing from footprint"
        row = rows[code]
        assert row["total_in_ml"] == pytest.approx(30.0)
        assert row["total_out_ml"] == pytest.approx(ml, abs=1e-6)
        # This week's cell (last column) carries the same flows.
        cell = row["cells"][-1]
        assert cell["in_ml"] == pytest.approx(30.0)
        assert cell["out_ml"] == pytest.approx(ml, abs=1e-6)
        assert cell["net_ml"] == pytest.approx(30.0 - ml, abs=1e-6)


def test_flow_is_tenant_scoped(client, populated):
    other = register_studio(client)
    r = client.get("/v1/dashboard/flow", headers=other["headers"])
    stages = {p["stage"]: p["count"] for p in r.json()["pipeline"]}
    assert stages["clients"] == 0
    assert r.json()["inventory_footprint"]["rows"] == []
