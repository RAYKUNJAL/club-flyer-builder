import os
import sys
import tempfile
import uuid
from io import BytesIO

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.mkdtemp(prefix="sbi-test-")
os.environ["SBI_DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["SBI_UPLOAD_DIR"] = f"{_TMP}/uploads"
os.environ["SBI_FRONTEND_DIST"] = f"{_TMP}/no-dist"

from fastapi.testclient import TestClient  # noqa: E402

from app.colorscience import lab_to_srgb  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed import DEFAULT_CARD_PATCHES  # noqa: E402


@pytest.fixture(scope="session")
def client():
    app = create_app(seed_demo=True)
    with TestClient(app) as c:
        yield c


def register_studio(client, role_extra=None) -> dict:
    """Register a fresh studio; returns owner auth headers and ids."""
    email = f"owner-{uuid.uuid4().hex[:10]}@studio.test"
    r = client.post("/v1/auth/register-studio", json={
        "studio_name": f"Studio {uuid.uuid4().hex[:6]}",
        "name": "Owner",
        "email": email,
        "password": "password-123",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    headers = {"Authorization": f"Bearer {data['token']}"}
    client.post("/v1/auth/acknowledge", headers=headers)
    return {"headers": headers, "user": data["user"], "tenant": data["tenant"], "email": email}


def create_staff(client, owner_headers, role) -> dict:
    email = f"{role}-{uuid.uuid4().hex[:10]}@studio.test"
    r = client.post("/v1/auth/users", headers=owner_headers, json={
        "name": role.title(), "email": email, "password": "password-123", "role": role,
    })
    assert r.status_code == 201, r.text
    r = client.post("/v1/auth/login", json={"email": email, "password": "password-123"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    return {"headers": headers, "user": r.json()["user"]}


def create_client_and_case(client, headers, consents=("treatment", "photography")) -> dict:
    r = client.post("/v1/clients", headers=headers, json={"legal_name": "Test Client"})
    assert r.status_code == 201, r.text
    c = r.json()
    for kind in consents:
        r2 = client.post(f"/v1/clients/{c['id']}/consents", headers=headers,
                         json={"kind": kind, "granted": True})
        assert r2.status_code == 201
    r = client.post("/v1/cases", headers=headers, json={
        "client_id": c["id"], "case_type": "vitiligo_camouflage",
    })
    assert r.status_code == 201, r.text
    return {"client": c, "case": r.json()}


SYNTH_MEASURED_PIGMENTS = [
    ("P-Y", "primary_yellow", [85.0, 5.0, 78.0]),
    ("P-R", "primary_red", [45.0, 62.0, 38.0]),
    ("P-B", "primary_blue", [35.0, 12.0, -48.0]),
    ("P-W", "white", [96.0, 0.5, 2.0]),
    ("P-K", "black", [12.0, 0.5, -1.0]),
]


def create_measured_kit(client, headers, expiry="2027-12-31") -> dict:
    """Create a kit whose dataset is flagged 'measured' (studio-entered swatch data)."""
    products = {}
    lots = {}
    for code, role, _lab in SYNTH_MEASURED_PIGMENTS:
        r = client.post("/v1/pigment-products", headers=headers, json={
            "manufacturer": "TestPigments", "product_name": f"Test {code}",
            "internal_code": code, "color_role": role,
        })
        assert r.status_code == 201, r.text
        products[code] = r.json()
        r = client.post("/v1/pigment-lots", headers=headers, json={
            "product_id": products[code]["id"], "lot_number": f"LOT-{code}-1",
            "expiry_date": expiry, "quantity_ml": 30.0,
        })
        assert r.status_code == 201, r.text
        lots[code] = r.json()
    r = client.post("/v1/pigment-kits", headers=headers, json={
        "name": "Test Measured Kit", "dataset_version": "kit-test-2026-001",
        "data_source": "measured",
        "pigments": [{"product_id": products[c]["id"], "code": c} for c in products],
    })
    assert r.status_code == 201, r.text
    kit = r.json()

    from app.formula.mixtures import synthetic_demo_samples

    for s in synthetic_demo_samples():
        ratios = {c: round(v, 6) for c, v in s.ratios.items()}
        drift = round(1.0 - sum(ratios.values()), 6)
        first = next(iter(ratios))
        ratios[first] = round(ratios[first] + drift, 6)
        r = client.post(f"/v1/pigment-kits/{kit['id']}/mixture-samples", headers=headers, json={
            "ratios": ratios, "lab": list(s.lab), "source": "measured",
        })
        assert r.status_code == 201, r.text
    return {
        "kit": kit,
        "products": products,
        "lots": lots,
        "lot_selection": {c: lots[c]["id"] for c in lots},
    }


def make_capture_image(
    skin_lab=(59.0, 13.0, 20.0),
    distort=(0.94, 0.99, 0.90),
    size=(800, 600),
    seed=1,
) -> dict:
    """Synthetic calibrated-capture photo: card patch row + skin field,
    with a channel cast and sensor noise. Returns PNG bytes plus the
    card/skin rectangles."""
    from PIL import Image

    rng = np.random.default_rng(seed)
    w, h = size
    skin_rgb = np.array(lab_to_srgb(tuple(skin_lab)), dtype=np.float64)
    img = np.ones((h, w, 3), dtype=np.float64) * skin_rgb

    card_rects = []
    for i, patch in enumerate(DEFAULT_CARD_PATCHES):
        rgb = np.array(lab_to_srgb(tuple(patch["lab"])), dtype=np.float64)
        x, y = 40 + i * 120, 20
        img[y : y + 80, x : x + 100] = rgb
        card_rects.append({"x": x + 15, "y": y + 15, "w": 70, "h": 50})

    img *= np.array(distort)
    img += rng.normal(0.0, 3.0, img.shape)
    img = np.clip(img, 0, 253).astype(np.uint8)

    buf = BytesIO()
    Image.fromarray(img, "RGB").save(buf, "PNG")
    return {
        "png": buf.getvalue(),
        "card_rects": card_rects,
        "skin_rect": {"x": 150, "y": 250, "w": 300, "h": 200},
    }


def calibrated_measurement(client, headers, case_id, skin_lab=(59.0, 13.0, 20.0)) -> dict:
    """Run the full calibrated capture flow (3 images) and return the analysis."""
    cards = client.get("/v1/reference-cards", headers=headers).json()
    card_id = cards[0]["id"]
    r = client.post("/v1/captures", headers=headers, json={
        "case_id": case_id, "mode": "calibrated", "reference_card_id": card_id,
    })
    assert r.status_code == 201, r.text
    capture = r.json()
    for seed in (1, 2, 3):
        art = make_capture_image(skin_lab=skin_lab, seed=seed)
        r = client.post(
            f"/v1/captures/{capture['id']}/images", headers=headers,
            files={"file": ("cap.png", art["png"], "image/png")},
        )
        assert r.status_code == 201, r.text
        image = r.json()
        assert image["grade"] == "pass", image["quality"]
        r = client.post(f"/v1/images/{image['id']}/card-patches", headers=headers,
                        json={"patches": art["card_rects"]})
        assert r.status_code == 200, r.text
        assert r.json()["passed"], r.json()
        r = client.post(f"/v1/images/{image['id']}/skin-patches", headers=headers,
                        json={"patches": [art["skin_rect"]]})
        assert r.status_code == 201, r.text
    r = client.post(f"/v1/captures/{capture['id']}/analyze", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def locked_formula(client, headers, kit_bundle, case_id, measurement_id, purpose="full_session") -> dict:
    """Generate -> swatch -> measure -> approve -> lock; returns the locked formula."""
    r = client.post("/v1/formulas/generate", headers=headers, json={
        "target_measurement_id": measurement_id,
        "pigment_kit_id": kit_bundle["kit"]["id"],
        "case_id": case_id,
        "purpose": purpose,
        "total_drops": 20,
        "lot_selection": kit_bundle["lot_selection"],
    })
    assert r.status_code == 201, r.text
    formula = r.json()
    r = client.post("/v1/swatches", headers=headers, json={"formula_id": formula["id"]})
    assert r.status_code == 201, r.text
    swatch = r.json()
    r = client.post(f"/v1/swatches/{swatch['id']}/measure", headers=headers, json={
        "lab": formula["predicted_lab"], "source_type": "instrument",
    })
    assert r.status_code == 200, r.text
    r = client.post(f"/v1/formulas/{formula['id']}/approve", headers=headers)
    assert r.status_code == 200, r.text
    r = client.post(f"/v1/formulas/{formula['id']}/lock", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()
