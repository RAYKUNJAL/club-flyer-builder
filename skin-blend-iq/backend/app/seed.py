"""Seed data: reference card definitions plus an optional demo studio.

The demo studio ships with the synthetic five-pigment kit (P-Y, P-R,
P-B, P-W, P-K). Its dataset is flagged data_source='synthetic', so every
formula generated from it is watermarked non-treatment-grade and the
safety block prevents any treatment session from using it (Appendix B
warning 1).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .formula.mixtures import SYNTHETIC_KIT_DATASET_VERSION, synthetic_demo_samples
from .models import (
    KitPigment,
    MixtureSampleRow,
    PigmentKit,
    PigmentLot,
    PigmentProduct,
    ReferenceCard,
    Tenant,
    User,
)

# A compact 6-patch calibration card (neutral ramp + skin-relevant chromatic
# patches), values in CIE L*a*b* (D65, 2 deg).
DEFAULT_CARD_PATCHES = [
    {"name": "white", "lab": [95.0, 0.0, 0.0]},
    {"name": "gray-70", "lab": [70.0, 0.0, 0.0]},
    {"name": "gray-40", "lab": [40.0, 0.0, 0.0]},
    {"name": "black", "lab": [10.0, 0.0, 0.0]},
    {"name": "skin-light", "lab": [70.0, 15.0, 20.0]},
    {"name": "skin-deep", "lab": [40.0, 18.0, 22.0]},
]

DEMO_PIGMENTS = [
    ("P-Y", "primary_yellow", "Demo Primary Yellow"),
    ("P-R", "primary_red", "Demo Primary Red"),
    ("P-B", "primary_blue", "Demo Primary Blue"),
    ("P-W", "white", "Demo White"),
    ("P-K", "black", "Demo Black"),
]


def seed_reference_card(db: Session) -> ReferenceCard:
    card = db.execute(
        select(ReferenceCard).where(ReferenceCard.name == "SBI Calibration Card v1")
    ).scalar_one_or_none()
    if card is None:
        card = ReferenceCard(name="SBI Calibration Card v1", patches=DEFAULT_CARD_PATCHES)
        db.add(card)
        db.flush()
    return card


def seed_demo_studio(db: Session) -> dict | None:
    if db.execute(select(User).where(User.email == "demo@skinblendiq.test")).scalar_one_or_none():
        return None
    tenant = Tenant(name="Demo Studio")
    db.add(tenant)
    db.flush()
    owner = User(
        tenant_id=tenant.id, email="demo@skinblendiq.test", name="Demo Owner",
        role="owner", password_hash=hash_password("demo-password-123"),
    )
    db.add(owner)
    db.flush()

    products = {}
    for code, role, name in DEMO_PIGMENTS:
        p = PigmentProduct(
            tenant_id=tenant.id, manufacturer="Demo Pigments Inc", brand_line="Synthetic Demo",
            product_name=name, internal_code=code, color_role=role,
        )
        db.add(p)
        db.flush()
        products[code] = p
        db.add(PigmentLot(
            tenant_id=tenant.id, product_id=p.id, lot_number=f"DEMO-{code}-001",
            expiry_date="2027-12-31", quantity_ml=30.0,
        ))

    kit = PigmentKit(
        tenant_id=tenant.id, name="Synthetic Demo Kit (prototype only)",
        dataset_version=SYNTHETIC_KIT_DATASET_VERSION, data_source="synthetic",
    )
    db.add(kit)
    db.flush()
    for code, p in products.items():
        db.add(KitPigment(kit_id=kit.id, product_id=p.id, code=code))
    for s in synthetic_demo_samples():
        db.add(MixtureSampleRow(
            tenant_id=tenant.id, kit_id=kit.id, ratios=s.ratios,
            lab=list(s.lab), source="synthetic", recorded_by=owner.id,
        ))
    db.flush()
    return {"tenant_id": tenant.id, "owner_email": owner.email, "kit_id": kit.id}


def seed(db: Session, demo: bool = True) -> None:
    seed_reference_card(db)
    if demo:
        seed_demo_studio(db)
    db.commit()
