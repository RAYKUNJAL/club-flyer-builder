from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user, tenant_get
from ..colorscience import delta_e_2000, delta_e_76, lab_to_srgb
from ..db import get_db
from ..formula import MODEL_VERSION
from ..formula.mixtures import KitModel, MixtureSample
from ..formula.quantize import drops_to_ratios, quantize_drops, quantization_error
from ..formula.scaling import (
    DEFAULT_DROP_VOLUME_ML,
    VOLUME_PRESETS_ML,
    drops_to_ml,
    scale_to_volume,
)
from ..formula.solver import MAX_ROUNDING_PENALTY_DE, solve
from ..models import (
    Batch,
    Case,
    ColorMeasurement,
    Formula,
    FormulaAdjustment,
    FormulaIngredient,
    InventoryTransaction,
    KitPigment,
    MixtureSampleRow,
    PigmentKit,
    PigmentLot,
    PigmentProduct,
    Swatch,
    SwatchMeasurement,
    User,
)
from ..serialize import to_dict
from .pigments_router import lot_is_blocked

router = APIRouter(prefix="/v1", tags=["formulas"])

# Formula state machine (spec section 10).
ADJUSTABLE_STATES = {"draft", "swatch_prepared", "swatch_measured", "artist_adjusted"}
SWATCH_PREPARABLE_STATES = {"draft", "artist_adjusted", "swatch_prepared"}


class GenerateIn(BaseModel):
    target_measurement_id: str
    pigment_kit_id: str
    case_id: str | None = None
    purpose: str = Field(default="full_session", pattern="^(test_spot|full_session|touch_up)$")
    total_drops: int = Field(default=20, gt=0, le=200)
    lot_selection: dict[str, str]  # pigment code -> lot id
    excluded_pigments: list[str] = []
    locked_pigments: dict[str, float] = {}
    max_pigments: int | None = None


class QuantizeIn(BaseModel):
    total_drops: int = Field(gt=0, le=200)


class AdjustIn(BaseModel):
    drops: dict[str, int]
    reason: str = Field(min_length=3)


class SwatchIn(BaseModel):
    formula_id: str
    substrate: str = "practice-skin"


class SwatchMeasureIn(BaseModel):
    lab: list[float] = Field(min_length=3, max_length=3)
    source_type: str = Field(default="instrument", pattern="^(instrument|capture|manual)$")


class ScaleIn(BaseModel):
    preset: str | None = None  # e.g. "1/2_fl_oz"
    total_ml: float | None = None
    drop_volume_ml: float = DEFAULT_DROP_VOLUME_ML


class BatchIn(BaseModel):
    formula_id: str
    preset: str | None = None
    total_ml: float | None = None
    planned_zones: list[str] = []
    drop_volume_ml: float = DEFAULT_DROP_VOLUME_ML


class UsageIn(BaseModel):
    quantity_used_ml: float = Field(ge=0)
    quantity_discarded_ml: float = Field(ge=0)


def build_kit_model(db: Session, kit: PigmentKit) -> KitModel:
    codes = [p.code for p in db.execute(
        select(KitPigment).where(KitPigment.kit_id == kit.id)
    ).scalars()]
    rows = db.execute(
        select(MixtureSampleRow).where(MixtureSampleRow.kit_id == kit.id)
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=422, detail="Kit has no mixture samples; calibrate it first")
    samples = [MixtureSample(ratios=r.ratios, lab=tuple(r.lab), source=r.source) for r in rows]
    try:
        return KitModel(
            codes=codes, samples=samples,
            dataset_version=kit.dataset_version, data_source=kit.data_source,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _validate_lots(
    db: Session, tenant_id: str, kit: PigmentKit, lot_selection: dict[str, str]
) -> dict[str, PigmentLot]:
    """Every kit code must map to an unblocked lot of the right product."""
    kit_pigments = {
        p.code: p.product_id
        for p in db.execute(select(KitPigment).where(KitPigment.kit_id == kit.id)).scalars()
    }
    missing = set(kit_pigments) - set(lot_selection)
    if missing:
        raise HTTPException(status_code=422, detail=f"No lot selected for pigments: {sorted(missing)}")
    lots: dict[str, PigmentLot] = {}
    blocked: dict[str, str] = {}
    for code, lot_id in lot_selection.items():
        if code not in kit_pigments:
            raise HTTPException(status_code=422, detail=f"Code {code} is not in this kit")
        lot = tenant_get(db, PigmentLot, lot_id, tenant_id, "lot")
        if lot.product_id != kit_pigments[code]:
            raise HTTPException(status_code=422, detail=f"Lot for {code} belongs to a different product")
        reason = lot_is_blocked(lot)
        if reason:
            blocked[code] = reason
        lots[code] = lot
    if blocked:
        raise HTTPException(
            status_code=409,
            detail={"error": "blocked_lots", "blocked": blocked,
                    "message": "Recalled, expired, or quarantined lots cannot be used."},
        )
    return lots


def _formula_out(db: Session, f: Formula) -> dict:
    out = to_dict(f)
    ingredients = db.execute(
        select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
    ).scalars().all()
    out["recipe"] = {i.code: i.drops for i in ingredients}
    out["ingredients"] = []
    for i in ingredients:
        lot = db.get(PigmentLot, i.pigment_lot_id)
        product = db.get(PigmentProduct, lot.product_id) if lot else None
        out["ingredients"].append({
            "code": i.code,
            "drops": i.drops,
            "lot_id": i.pigment_lot_id,
            "lot_number": lot.lot_number if lot else None,
            "expiry_date": lot.expiry_date if lot else None,
            "product_name": product.product_name if product else None,
            "manufacturer": product.manufacturer if product else None,
        })
    if f.predicted_lab:
        out["predicted_rgb_display"] = [round(v, 1) for v in lab_to_srgb(tuple(f.predicted_lab))]
    if f.target_lab:
        out["target_rgb_display"] = [round(v, 1) for v in lab_to_srgb(tuple(f.target_lab))]
    return out


def _replace_ingredients(db: Session, f: Formula, drops: dict[str, int], lots: dict[str, str]):
    for row in db.execute(
        select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
    ).scalars():
        db.delete(row)
    db.flush()
    for code, n in drops.items():
        db.add(FormulaIngredient(
            formula_id=f.id, pigment_lot_id=lots[code], code=code, drops=n,
        ))


def _lots_by_code(db: Session, f: Formula) -> dict[str, str]:
    return {
        i.code: i.pigment_lot_id
        for i in db.execute(
            select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
        ).scalars()
    }


@router.post("/formulas/generate", status_code=201)
def generate_formula(body: GenerateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = tenant_get(db, ColorMeasurement, body.target_measurement_id, user.tenant_id, "measurement")
    kit = tenant_get(db, PigmentKit, body.pigment_kit_id, user.tenant_id, "kit")
    if body.case_id:
        tenant_get(db, Case, body.case_id, user.tenant_id, "case")
    lots = _validate_lots(db, user.tenant_id, kit, body.lot_selection)
    model = build_kit_model(db, kit)

    target_lab = (target.lab_l, target.lab_a, target.lab_b)
    result = solve(
        model,
        target_lab,
        total_drops=body.total_drops,
        target_uncertainty=target.delta_e_uncertainty or 0.0,
        excluded=body.excluded_pigments,
        locked=body.locked_pigments,
        max_pigments=body.max_pigments,
    )
    best = result["candidates"][0]

    treatment_grade = bool(target.treatment_grade) and kit.data_source == "measured"
    warnings = list(result["warnings"])
    if kit.data_source == "synthetic":
        warnings.append(
            "PROTOTYPE ONLY: this kit uses synthetic pigment data. "
            "The formula must never be used on a person."
        )
    if not target.treatment_grade:
        warnings.append("Target measurement is not treatment-grade (uncalibrated or failed quality gates).")
    if best.rounding_delta_e > MAX_ROUNDING_PENALTY_DE:
        warnings.append(
            f"Cap size of {body.total_drops} drops adds excessive rounding error "
            f"(+{best.rounding_delta_e} ΔE00); use a larger total."
        )

    f = Formula(
        tenant_id=user.tenant_id,
        case_id=body.case_id,
        purpose=body.purpose,
        target_measurement_id=target.id,
        pigment_kit_id=kit.id,
        model_version=MODEL_VERSION,
        dataset_version=kit.dataset_version,
        cap_total_drops=body.total_drops,
        continuous_ratios=best.ratios,
        target_lab=[round(v, 3) for v in target_lab],
        predicted_lab=list(best.predicted_lab),
        predicted_delta_e00=best.delta_e_2000,
        predicted_delta_e76=best.delta_e_76,
        rounding_delta_e=best.rounding_delta_e,
        confidence=best.confidence,
        gamut_status=result["gamut_status"],
        treatment_grade=treatment_grade,
        status="draft",
        warnings=warnings,
        created_by=user.id,
    )
    db.add(f)
    db.flush()
    _replace_ingredients(db, f, best.drops, {c: lots[c].id for c in lots})
    audit.record(
        db, user.tenant_id, "formula.generated", "formula", f.id, user.id,
        {
            "model_version": MODEL_VERSION,
            "dataset_version": kit.dataset_version,
            "gamut_status": result["gamut_status"],
            "predicted_delta_e00": best.delta_e_2000,
            "treatment_grade": treatment_grade,
            "recipe": best.drops,
            "continuous_ratios": best.ratios,
        },
    )
    db.commit()

    out = _formula_out(db, f)
    out["required_verification"] = "external_swatch"
    out["alternatives"] = [
        {
            "recipe": c.drops,
            "predicted_lab": list(c.predicted_lab),
            "predicted_delta_e00": c.delta_e_2000,
            "confidence": c.confidence,
            "n_pigments": c.n_pigments,
        }
        for c in result["candidates"][1:]
    ]
    out["gamut_distance"] = result["gamut_distance"]
    return out


@router.get("/formulas")
def list_formulas(case_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Formula).where(Formula.tenant_id == user.tenant_id).order_by(Formula.created_at.desc())
    if case_id:
        q = q.where(Formula.case_id == case_id)
    return [_formula_out(db, f) for f in db.execute(q).scalars().all()]


@router.get("/formulas/{formula_id}")
def get_formula(formula_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = tenant_get(db, Formula, formula_id, user.tenant_id, "formula")
    out = _formula_out(db, f)
    swatches = db.execute(select(Swatch).where(Swatch.formula_id == f.id)).scalars().all()
    out["swatches"] = []
    for s in swatches:
        d = to_dict(s)
        ms = db.execute(select(SwatchMeasurement).where(SwatchMeasurement.swatch_id == s.id)).scalars().all()
        d["measurements"] = [to_dict(m) for m in ms]
        out["swatches"].append(d)
    adjustments = db.execute(
        select(FormulaAdjustment).where(FormulaAdjustment.formula_id == f.id)
    ).scalars().all()
    out["adjustments"] = [to_dict(a) for a in adjustments]
    return out


@router.post("/formulas/{formula_id}/quantize")
def requantize(formula_id: str, body: QuantizeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = tenant_get(db, Formula, formula_id, user.tenant_id, "formula")
    if f.status not in ADJUSTABLE_STATES:
        raise HTTPException(status_code=409, detail=f"Cannot re-quantize a formula in state '{f.status}'")
    kit = db.get(PigmentKit, f.pigment_kit_id)
    model = build_kit_model(db, kit)
    drops = quantize_drops(f.continuous_ratios, body.total_drops)
    pred = model.predict_lab(drops_to_ratios(drops))
    target = tuple(f.target_lab)
    de00 = round(delta_e_2000(pred, target), 3)
    cont_de = round(delta_e_2000(model.predict_lab(f.continuous_ratios), target), 3)

    f.cap_total_drops = body.total_drops
    f.predicted_lab = [round(v, 3) for v in pred]
    f.predicted_delta_e00 = de00
    f.predicted_delta_e76 = round(delta_e_76(pred, target), 3)
    f.rounding_delta_e = round(de00 - cont_de, 3)
    lots = _lots_by_code(db, f)
    _replace_ingredients(db, f, drops, lots)
    db.add(f)
    audit.record(db, user.tenant_id, "formula.requantized", "formula", f.id, user.id,
                 {"total_drops": body.total_drops, "recipe": drops, "predicted_delta_e00": de00})
    db.commit()
    out = _formula_out(db, f)
    out["quantization_error"] = quantization_error(f.continuous_ratios, drops)
    if f.rounding_delta_e > MAX_ROUNDING_PENALTY_DE:
        out.setdefault("warnings", []).append("Excessive rounding error at this cap size.")
    return out


@router.post("/formulas/{formula_id}/adjust")
def adjust_formula(formula_id: str, body: AdjustIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = tenant_get(db, Formula, formula_id, user.tenant_id, "formula")
    if f.status not in ADJUSTABLE_STATES:
        raise HTTPException(
            status_code=409,
            detail=f"Formula in state '{f.status}' is immutable; create a new version instead",
        )
    if any(v < 0 for v in body.drops.values()):
        raise HTTPException(status_code=422, detail="Drop counts cannot be negative")
    total = sum(body.drops.values())
    if total <= 0:
        raise HTTPException(status_code=422, detail="Recipe must contain at least one drop")
    lots = _lots_by_code(db, f)
    unknown = set(body.drops) - set(lots)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown pigment codes: {sorted(unknown)}")

    ingredients = db.execute(
        select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
    ).scalars().all()
    before = {i.code: i.drops for i in ingredients}

    kit = db.get(PigmentKit, f.pigment_kit_id)
    model = build_kit_model(db, kit)
    drops = {c: n for c, n in body.drops.items()}
    pred = model.predict_lab(drops_to_ratios(drops))
    target = tuple(f.target_lab)

    f.cap_total_drops = total
    f.predicted_lab = [round(v, 3) for v in pred]
    f.predicted_delta_e00 = round(delta_e_2000(pred, target), 3)
    f.predicted_delta_e76 = round(delta_e_76(pred, target), 3)
    f.status = "artist_adjusted"
    _replace_ingredients(db, f, drops, lots)
    adj = FormulaAdjustment(
        tenant_id=user.tenant_id, formula_id=f.id,
        before_drops=before, after_drops=drops, reason=body.reason, adjusted_by=user.id,
    )
    db.add_all([f, adj])
    db.flush()
    audit.record(db, user.tenant_id, "formula.adjusted", "formula", f.id, user.id,
                 {"before": before, "after": drops, "reason": body.reason})
    db.commit()
    out = _formula_out(db, f)
    out["note"] = "Adjustment requires a new external swatch before approval."
    return out


@router.post("/swatches", status_code=201)
def prepare_swatch(body: SwatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = tenant_get(db, Formula, body.formula_id, user.tenant_id, "formula")
    if f.status not in SWATCH_PREPARABLE_STATES:
        raise HTTPException(status_code=409, detail=f"Cannot prepare swatch in state '{f.status}'")
    s = Swatch(tenant_id=user.tenant_id, formula_id=f.id, substrate=body.substrate, prepared_by=user.id)
    f.status = "swatch_prepared"
    db.add_all([s, f])
    db.flush()
    audit.record(db, user.tenant_id, "swatch.prepared", "swatch", s.id, user.id,
                 {"formula_id": f.id})
    db.commit()
    return to_dict(s)


@router.post("/swatches/{swatch_id}/measure")
def measure_swatch(swatch_id: str, body: SwatchMeasureIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = tenant_get(db, Swatch, swatch_id, user.tenant_id, "swatch")
    f = db.get(Formula, s.formula_id)
    if f.status != "swatch_prepared":
        raise HTTPException(status_code=409, detail=f"Formula is in state '{f.status}', expected swatch_prepared")
    m = ColorMeasurement(
        tenant_id=user.tenant_id,
        source_type="swatch",
        lab_l=body.lab[0], lab_a=body.lab[1], lab_b=body.lab[2],
        rgb_display=[round(v, 1) for v in lab_to_srgb(tuple(body.lab))],
        treatment_grade=body.source_type == "instrument",
    )
    db.add(m)
    db.flush()
    de = round(delta_e_2000(tuple(body.lab), tuple(f.target_lab)), 3)
    sm = SwatchMeasurement(
        tenant_id=user.tenant_id, swatch_id=s.id, measurement_id=m.id, delta_e00_vs_target=de,
    )
    s.status = "measured"
    f.status = "swatch_measured"
    db.add_all([sm, s, f])
    db.flush()
    audit.record(db, user.tenant_id, "swatch.measured", "swatch", s.id, user.id,
                 {"delta_e00_vs_target": de, "formula_id": f.id})
    db.commit()
    return {"swatch": to_dict(s), "delta_e00_vs_target": de, "measurement": to_dict(m)}


@router.post("/formulas/{formula_id}/approve")
def approve_formula(formula_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = tenant_get(db, Formula, formula_id, user.tenant_id, "formula")
    if user.professional_ack_at is None:
        raise HTTPException(
            status_code=403,
            detail="Professional acknowledgment required before approving formulas (POST /v1/auth/acknowledge)",
        )
    if user.role == "trainee":
        raise HTTPException(status_code=403, detail="Trainees cannot approve formulas; request senior approval")
    if f.status != "swatch_measured":
        raise HTTPException(
            status_code=409,
            detail="External swatch verification is mandatory before approval "
                   f"(state is '{f.status}', expected 'swatch_measured')",
        )
    f.status = "approved"
    f.approved_by = user.id
    f.approved_at = datetime.now(timezone.utc)
    db.add(f)
    audit.record(db, user.tenant_id, "formula.approved", "formula", f.id, user.id)
    db.commit()
    return _formula_out(db, f)


@router.post("/formulas/{formula_id}/lock")
def lock_formula(formula_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = tenant_get(db, Formula, formula_id, user.tenant_id, "formula")
    if f.status != "approved":
        raise HTTPException(status_code=409, detail=f"Only approved formulas can be locked (state '{f.status}')")
    # Re-verify every lot at lock time: a recall may have landed since approval.
    for i in db.execute(select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)).scalars():
        lot = db.get(PigmentLot, i.pigment_lot_id)
        reason = lot_is_blocked(lot)
        if reason:
            raise HTTPException(
                status_code=409,
                detail=f"Lot {lot.lot_number} for {i.code} is now {reason}; formula cannot be locked",
            )
    f.status = "locked"
    f.locked_at = datetime.now(timezone.utc)
    db.add(f)
    audit.record(db, user.tenant_id, "formula.locked", "formula", f.id, user.id,
                 {"recipe": {i.code: i.drops for i in db.execute(
                     select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
                 ).scalars()}})
    db.commit()
    return _formula_out(db, f)


@router.post("/formulas/{formula_id}/new-version", status_code=201)
def new_version(formula_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Locked formulas are immutable; changes create a new draft version."""
    f = tenant_get(db, Formula, formula_id, user.tenant_id, "formula")
    ingredients = db.execute(
        select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
    ).scalars().all()
    nf = Formula(
        tenant_id=f.tenant_id, case_id=f.case_id, version=f.version + 1,
        parent_formula_id=f.id, purpose=f.purpose,
        target_measurement_id=f.target_measurement_id, pigment_kit_id=f.pigment_kit_id,
        model_version=f.model_version, dataset_version=f.dataset_version,
        cap_total_drops=f.cap_total_drops, continuous_ratios=f.continuous_ratios,
        target_lab=f.target_lab, predicted_lab=f.predicted_lab,
        predicted_delta_e00=f.predicted_delta_e00, predicted_delta_e76=f.predicted_delta_e76,
        rounding_delta_e=f.rounding_delta_e, confidence=f.confidence,
        gamut_status=f.gamut_status, treatment_grade=f.treatment_grade,
        status="draft", warnings=f.warnings, created_by=user.id,
    )
    db.add(nf)
    db.flush()
    for i in ingredients:
        db.add(FormulaIngredient(
            formula_id=nf.id, pigment_lot_id=i.pigment_lot_id, code=i.code, drops=i.drops,
        ))
    audit.record(db, user.tenant_id, "formula.new_version", "formula", nf.id, user.id,
                 {"parent": f.id, "version": nf.version})
    db.commit()
    return _formula_out(db, nf)


@router.post("/formulas/{formula_id}/scale")
def scale_formula(formula_id: str, body: ScaleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = tenant_get(db, Formula, formula_id, user.tenant_id, "formula")
    ingredients = db.execute(
        select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
    ).scalars().all()
    drops = {i.code: i.drops for i in ingredients}
    if body.total_ml is not None:
        total_ml = body.total_ml
    elif body.preset:
        if body.preset not in VOLUME_PRESETS_ML or VOLUME_PRESETS_ML[body.preset] is None:
            raise HTTPException(status_code=422, detail=f"Unknown preset '{body.preset}'")
        total_ml = VOLUME_PRESETS_ML[body.preset]
    else:
        result = drops_to_ml(drops, body.drop_volume_ml)
        result["basis"] = "drops"
        return result
    result = scale_to_volume(drops, total_ml)
    result["basis"] = body.preset or "custom_ml"
    result["estimated_total_drops"] = round(total_ml / body.drop_volume_ml)
    return result


@router.post("/batches", status_code=201)
def create_batch(body: BatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = tenant_get(db, Formula, body.formula_id, user.tenant_id, "formula")
    if f.status not in ("locked", "used"):
        raise HTTPException(status_code=409, detail="Batches can only be prepared from locked formulas")
    ingredients = db.execute(
        select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
    ).scalars().all()
    drops = {i.code: i.drops for i in ingredients}
    lot_by_code = {i.code: i.pigment_lot_id for i in ingredients}

    if body.total_ml is not None:
        total_ml = body.total_ml
    elif body.preset:
        if body.preset not in VOLUME_PRESETS_ML or VOLUME_PRESETS_ML[body.preset] is None:
            raise HTTPException(status_code=422, detail=f"Unknown preset '{body.preset}'")
        total_ml = VOLUME_PRESETS_ML[body.preset]
    else:
        total_ml = drops_to_ml(drops, body.drop_volume_ml)["total_ml"]
    scaled = scale_to_volume(drops, total_ml)

    # Verify lots again and check + deduct inventory.
    for code, ml in scaled["ingredients_ml"].items():
        lot = db.get(PigmentLot, lot_by_code[code])
        reason = lot_is_blocked(lot)
        if reason:
            raise HTTPException(status_code=409, detail=f"Lot for {code} is {reason}")
        if lot.quantity_ml < ml:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient inventory for {code}: need {ml} mL, have {lot.quantity_ml} mL",
            )
    for code, ml in scaled["ingredients_ml"].items():
        lot = db.get(PigmentLot, lot_by_code[code])
        lot.quantity_ml = round(lot.quantity_ml - ml, 6)
        db.add(lot)
        db.add(InventoryTransaction(
            tenant_id=user.tenant_id, lot_id=lot.id, delta_ml=-ml, kind="use",
            note=f"Batch for formula {f.id}", recorded_by=user.id,
        ))

    count = len(db.execute(select(Batch.id).where(Batch.tenant_id == user.tenant_id)).all())
    code = f"SBI-B-{8800 + count + 1}"
    lots_desc = ", ".join(
        f"{i.code}:{db.get(PigmentLot, i.pigment_lot_id).lot_number}" for i in ingredients
    )
    label = (
        "SKIN BLEND IQ\n"
        f"Formula {f.id} v{f.version}\n"
        f"Batch {code}\n"
        f"Prepared {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Total {scaled['total_ml']} mL\n"
        f"Zones {', '.join(body.planned_zones) if body.planned_zones else '-'}\n"
        f"Pigment lots: {lots_desc}\n"
        f"Prepared by: {user.name}\n"
        "Discard rule: studio policy — never return mixed pigment to a bottle"
    )
    batch = Batch(
        tenant_id=user.tenant_id, formula_id=f.id, display_code=code,
        total_ml=scaled["total_ml"], ingredients_ml=scaled["ingredients_ml"],
        rounding_differences_ml=scaled["rounding_differences_ml"],
        planned_zones=body.planned_zones, prepared_by=user.id, label_text=label,
    )
    db.add(batch)
    db.flush()
    audit.record(db, user.tenant_id, "batch.prepared", "batch", batch.id, user.id,
                 {"formula_id": f.id, "total_ml": scaled["total_ml"]})
    db.commit()
    return to_dict(batch)


@router.post("/batches/{batch_id}/usage")
def record_batch_usage(batch_id: str, body: UsageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    batch = tenant_get(db, Batch, batch_id, user.tenant_id, "batch")
    if body.quantity_used_ml + body.quantity_discarded_ml > batch.total_ml + 1e-6:
        raise HTTPException(status_code=422, detail="Used + discarded exceeds prepared quantity")
    batch.quantity_used_ml = body.quantity_used_ml
    batch.quantity_discarded_ml = body.quantity_discarded_ml
    db.add(batch)
    audit.record(db, user.tenant_id, "batch.usage_recorded", "batch", batch.id, user.id,
                 {"used_ml": body.quantity_used_ml, "discarded_ml": body.quantity_discarded_ml})
    db.commit()
    return to_dict(batch)
