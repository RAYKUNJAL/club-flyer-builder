from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user, require_role, tenant_get
from ..db import get_db
from ..models import (
    Case,
    Client,
    DropperCalibration,
    Formula,
    FormulaIngredient,
    InventoryTransaction,
    KitPigment,
    MixtureSampleRow,
    PigmentKit,
    PigmentLot,
    PigmentProduct,
    Recall,
    TreatmentSession,
    User,
)
from ..serialize import to_dict

router = APIRouter(prefix="/v1", tags=["pigments"])


class ProductIn(BaseModel):
    manufacturer: str = Field(min_length=1)
    brand_line: str | None = None
    product_name: str = Field(min_length=1)
    internal_code: str = Field(min_length=1)
    color_role: str = Field(min_length=1)
    regulatory_region: str = "US"
    spectral_data_available: bool = False


class LotIn(BaseModel):
    product_id: str
    lot_number: str = Field(min_length=1)
    expiry_date: str
    quantity_ml: float = 15.0


class KitIn(BaseModel):
    name: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    data_source: str = Field(default="measured", pattern="^(measured|synthetic)$")
    pigments: list[dict]  # [{product_id, code}]


class MixtureSampleIn(BaseModel):
    ratios: dict[str, float]
    lab: list[float] = Field(min_length=3, max_length=3)
    source: str = Field(default="measured", pattern="^(measured|synthetic)$")


class DropperCalIn(BaseModel):
    product_id: str | None = None
    drop_volume_ml_mean: float = Field(gt=0)
    drop_volume_ml_std: float = Field(ge=0)
    sample_count: int = Field(ge=3)
    tolerance_pct: float = 10.0
    operator: str | None = None


class QuarantineIn(BaseModel):
    reason: str = Field(min_length=1)


class InventoryTxIn(BaseModel):
    delta_ml: float
    kind: str = Field(pattern="^(receive|use|discard|adjust)$")
    note: str | None = None


def lot_is_blocked(lot: PigmentLot) -> str | None:
    """Non-negotiable rule 9: recalled, expired, unknown, quarantined lots are blocked."""
    if lot.status in ("recalled", "quarantined", "depleted"):
        return lot.status
    try:
        if date.fromisoformat(lot.expiry_date) < date.today():
            return "expired"
    except ValueError:
        return "unknown_expiry"
    return None


@router.post("/pigment-products", status_code=201)
def create_product(body: ProductIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = PigmentProduct(tenant_id=user.tenant_id, **body.model_dump())
    db.add(p)
    db.flush()
    audit.record(db, user.tenant_id, "pigment.product_created", "pigment_product", p.id, user.id)
    db.commit()
    return to_dict(p)


@router.get("/pigment-products")
def list_products(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(PigmentProduct).where(PigmentProduct.tenant_id == user.tenant_id)
    ).scalars().all()
    return [to_dict(r) for r in rows]


@router.post("/pigment-lots", status_code=201)
def create_lot(body: LotIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tenant_get(db, PigmentProduct, body.product_id, user.tenant_id, "product")
    try:
        date.fromisoformat(body.expiry_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="expiry_date must be an ISO date")
    lot = PigmentLot(tenant_id=user.tenant_id, **body.model_dump())
    db.add(lot)
    db.flush()
    db.add(InventoryTransaction(
        tenant_id=user.tenant_id, lot_id=lot.id, delta_ml=body.quantity_ml,
        kind="receive", recorded_by=user.id,
    ))
    audit.record(db, user.tenant_id, "pigment.lot_created", "pigment_lot", lot.id, user.id,
                 {"lot_number": body.lot_number})
    db.commit()
    return to_dict(lot)


@router.get("/pigment-lots")
def list_lots(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(PigmentLot).where(PigmentLot.tenant_id == user.tenant_id)
    ).scalars().all()
    out = []
    for lot in rows:
        d = to_dict(lot)
        d["blocked_reason"] = lot_is_blocked(lot)
        out.append(d)
    return out


@router.post("/pigment-lots/{lot_id}/quarantine")
def quarantine_lot(
    lot_id: str, body: QuarantineIn,
    user: User = Depends(require_role("senior")), db: Session = Depends(get_db),
):
    lot = tenant_get(db, PigmentLot, lot_id, user.tenant_id, "lot")
    lot.status = "quarantined"
    db.add(lot)
    audit.record(db, user.tenant_id, "pigment.lot_quarantined", "pigment_lot", lot.id, user.id,
                 {"reason": body.reason})
    db.commit()
    return to_dict(lot)


@router.post("/recalls", status_code=201)
def create_recall(
    body: QuarantineIn, lot_id: str,
    user: User = Depends(require_role("senior")), db: Session = Depends(get_db),
):
    lot = tenant_get(db, PigmentLot, lot_id, user.tenant_id, "lot")
    lot.status = "recalled"
    recall = Recall(tenant_id=user.tenant_id, lot_id=lot.id, reason=body.reason, created_by=user.id)
    db.add_all([lot, recall])
    db.flush()
    audit.record(db, user.tenant_id, "pigment.lot_recalled", "recall", recall.id, user.id,
                 {"lot_id": lot.id, "reason": body.reason})
    db.commit()
    return to_dict(recall)


@router.get("/recalls/{recall_id}/affected-clients")
def recall_affected_clients(recall_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Every client whose formula used the recalled lot (recall workflow step 3)."""
    recall = tenant_get(db, Recall, recall_id, user.tenant_id, "recall")
    rows = db.execute(
        select(Client, Case, Formula, TreatmentSession)
        .join(Case, Case.client_id == Client.id)
        .join(Formula, Formula.case_id == Case.id)
        .join(FormulaIngredient, FormulaIngredient.formula_id == Formula.id)
        .outerjoin(TreatmentSession, TreatmentSession.formula_id == Formula.id)
        .where(
            FormulaIngredient.pigment_lot_id == recall.lot_id,
            Client.tenant_id == user.tenant_id,
        )
    ).all()
    seen = {}
    for client, case, formula, session in rows:
        entry = seen.setdefault(client.id, {
            "client_id": client.id,
            "display_code": client.display_code,
            "legal_name": client.legal_name,
            "formulas": [],
            "treated": False,
        })
        entry["formulas"].append({"formula_id": formula.id, "status": formula.status, "case_id": case.id})
        if session is not None:
            entry["treated"] = True
    return {"recall_id": recall.id, "lot_id": recall.lot_id, "affected_clients": list(seen.values())}


@router.post("/pigment-lots/{lot_id}/inventory", status_code=201)
def inventory_tx(
    lot_id: str, body: InventoryTxIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    lot = tenant_get(db, PigmentLot, lot_id, user.tenant_id, "lot")
    new_qty = round(lot.quantity_ml + body.delta_ml, 4)
    if new_qty < 0:
        raise HTTPException(status_code=422, detail="Insufficient quantity in lot")
    lot.quantity_ml = new_qty
    if new_qty == 0:
        lot.status = "depleted" if lot.status == "active" else lot.status
    tx = InventoryTransaction(
        tenant_id=user.tenant_id, lot_id=lot.id, delta_ml=body.delta_ml,
        kind=body.kind, note=body.note, recorded_by=user.id,
    )
    db.add_all([lot, tx])
    db.flush()
    audit.record(db, user.tenant_id, "inventory.transaction", "pigment_lot", lot.id, user.id,
                 {"delta_ml": body.delta_ml, "kind": body.kind, "quantity_ml": new_qty})
    db.commit()
    return {"lot": to_dict(lot), "transaction": to_dict(tx)}


@router.post("/pigment-kits", status_code=201)
def create_kit(body: KitIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.pigments:
        raise HTTPException(status_code=422, detail="Kit needs at least one pigment")
    kit = PigmentKit(
        tenant_id=user.tenant_id, name=body.name,
        dataset_version=body.dataset_version, data_source=body.data_source,
    )
    db.add(kit)
    db.flush()
    for p in body.pigments:
        tenant_get(db, PigmentProduct, p["product_id"], user.tenant_id, "product")
        db.add(KitPigment(kit_id=kit.id, product_id=p["product_id"], code=p["code"]))
    audit.record(db, user.tenant_id, "pigment.kit_created", "pigment_kit", kit.id, user.id,
                 {"dataset_version": body.dataset_version, "data_source": body.data_source})
    db.commit()
    return to_dict(kit)


@router.get("/pigment-kits")
def list_kits(user: User = Depends(current_user), db: Session = Depends(get_db)):
    kits = db.execute(
        select(PigmentKit).where(PigmentKit.tenant_id == user.tenant_id)
    ).scalars().all()
    out = []
    for kit in kits:
        d = to_dict(kit)
        pigs = db.execute(select(KitPigment).where(KitPigment.kit_id == kit.id)).scalars().all()
        d["pigments"] = [{"product_id": p.product_id, "code": p.code} for p in pigs]
        d["sample_count"] = len(db.execute(
            select(MixtureSampleRow.id).where(MixtureSampleRow.kit_id == kit.id)
        ).all())
        out.append(d)
    return out


@router.post("/pigment-kits/{kit_id}/mixture-samples", status_code=201)
def add_mixture_sample(
    kit_id: str, body: MixtureSampleIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    kit = tenant_get(db, PigmentKit, kit_id, user.tenant_id, "kit")
    codes = {p.code for p in db.execute(select(KitPigment).where(KitPigment.kit_id == kit.id)).scalars()}
    unknown = set(body.ratios) - codes
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown pigment codes: {sorted(unknown)}")
    if abs(sum(body.ratios.values()) - 1.0) > 1e-6:
        raise HTTPException(status_code=422, detail="Ratios must sum to 1")
    row = MixtureSampleRow(
        tenant_id=user.tenant_id, kit_id=kit.id, ratios=body.ratios,
        lab=body.lab, source=body.source, recorded_by=user.id,
    )
    db.add(row)
    db.flush()
    audit.record(db, user.tenant_id, "pigment.mixture_sample_added", "mixture_sample", row.id, user.id)
    db.commit()
    return to_dict(row)


@router.post("/dropper-calibrations", status_code=201)
def add_dropper_calibration(
    body: DropperCalIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if body.product_id:
        tenant_get(db, PigmentProduct, body.product_id, user.tenant_id, "product")
    cv_pct = (body.drop_volume_ml_std / body.drop_volume_ml_mean) * 100.0
    cal = DropperCalibration(
        tenant_id=user.tenant_id,
        within_tolerance=cv_pct <= body.tolerance_pct,
        **body.model_dump(),
    )
    db.add(cal)
    db.flush()
    audit.record(db, user.tenant_id, "calibration.dropper_recorded", "dropper_calibration",
                 cal.id, user.id, {"cv_pct": round(cv_pct, 2), "within_tolerance": cal.within_tolerance})
    db.commit()
    out = to_dict(cal)
    if not cal.within_tolerance:
        out["warning"] = "Dropper variation exceeds tolerance; do not treat drops as reproducible."
    return out


@router.get("/dropper-calibrations")
def list_dropper_calibrations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(DropperCalibration).where(DropperCalibration.tenant_id == user.tenant_id)
    ).scalars().all()
    return [to_dict(r) for r in rows]
