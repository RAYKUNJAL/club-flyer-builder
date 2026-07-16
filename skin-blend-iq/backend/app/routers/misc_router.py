from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user, tenant_get
from ..db import get_db
from ..formula.scaling import coverage_estimate_ml
from ..models import (
    AuditEvent,
    Case,
    Client,
    ColorMeasurement,
    Formula,
    FormulaIngredient,
    PigmentLot,
    PigmentProduct,
    Swatch,
    SwatchMeasurement,
    TestSpot,
    TreatmentSession,
    User,
)
from ..serialize import to_dict

router = APIRouter(prefix="/v1", tags=["misc"])


class EstimateIn(BaseModel):
    consultation_fee: float = 0.0
    test_spot_fee: float = 0.0
    minimum_fee: float = 0.0
    area_sq_in: float = Field(gt=0)
    area_rate_per_sq_in: float = 0.0
    complexity_factor: float = 1.0
    hours: float = 0.0
    hourly_rate: float = 0.0
    supplies: float = 0.0
    travel: float = 0.0
    discount: float = 0.0


class CoverageIn(BaseModel):
    area_sq_cm: float = Field(gt=0)
    ml_per_sq_cm: float = Field(gt=0, default=0.02)
    passes: int = Field(gt=0, default=1)
    texture_factor: float = Field(gt=0, default=1.0)
    reserve_factor: float = Field(gt=0, default=1.2)


@router.get("/audit-events")
def list_audit_events(
    limit: int = 100, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    rows = db.execute(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == user.tenant_id)
        .order_by(AuditEvent.seq.desc())
        .limit(min(limit, 500))
    ).scalars().all()
    return [to_dict(r) for r in rows]


@router.get("/audit-events/verify")
def verify_audit_chain(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return audit.verify_chain(db, user.tenant_id)


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = user.tenant_id

    def count(model, *conds):
        return db.execute(
            select(func.count()).select_from(model).where(model.tenant_id == t, *conds)
        ).scalar_one()

    area_tiers = {
        "clients": count(Client),
        "cases": count(Case),
        "formulas": count(Formula),
        "locked_formulas": count(Formula, Formula.status.in_(["locked", "used", "followup_pending", "outcome_reviewed"])),
        "treatment_sessions": count(TreatmentSession),
        "test_spots_pending": count(TestSpot, TestSpot.status == "healing"),
        "blocked_lots": count(PigmentLot, PigmentLot.status.in_(["recalled", "quarantined"])),
        "active_lots": count(PigmentLot, PigmentLot.status == "active"),
    }
    return area_tiers


@router.get("/dashboard/flow")
def dashboard_flow(weeks: int = 8, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Chart data for the advanced dashboard, computed from real records.

    - pipeline: order-flow counts at each workflow stage
    - inventory_footprint: per-product weekly mL in (received) x out
      (used/discarded), from InventoryTransaction rows
    """
    from datetime import date, timedelta

    from ..models import (
        CaptureSession,
        HealedFollowUp,
        InventoryTransaction,
        SwatchMeasurement,
        TestSpot,
    )

    t = user.tenant_id

    def count(model, *conds):
        return db.execute(
            select(func.count()).select_from(model).where(model.tenant_id == t, *conds)
        ).scalar_one()

    swatch_verified = db.execute(
        select(func.count(func.distinct(Swatch.formula_id)))
        .select_from(SwatchMeasurement)
        .join(Swatch, Swatch.id == SwatchMeasurement.swatch_id)
        .where(SwatchMeasurement.tenant_id == t)
    ).scalar_one()

    pipeline = [
        {"stage": "clients", "label": "Clients", "count": count(Client)},
        {"stage": "cases", "label": "Cases opened", "count": count(Case)},
        {"stage": "captures", "label": "Capture sessions", "count": count(CaptureSession)},
        {"stage": "analyses", "label": "Skin analyses",
         "count": count(ColorMeasurement, ColorMeasurement.source_type != "swatch")},
        {"stage": "formulas", "label": "Formulas generated", "count": count(Formula)},
        {"stage": "swatch_verified", "label": "Swatch-verified", "count": swatch_verified},
        {"stage": "locked", "label": "Locked for treatment",
         "count": count(Formula, Formula.status.in_(
             ["locked", "used", "followup_pending", "outcome_reviewed"]))},
        {"stage": "test_spots", "label": "Test spots approved",
         "count": count(TestSpot, TestSpot.approved == True)},  # noqa: E712
        {"stage": "sessions", "label": "Treatment sessions", "count": count(TreatmentSession)},
        {"stage": "follow_ups", "label": "Healed follow-ups", "count": count(HealedFollowUp)},
    ]

    weeks = max(1, min(weeks, 26))
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_starts = [monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    week_keys = [w.isocalendar() for w in week_starts]
    week_labels = [f"{k.year}-W{k.week:02d}" for k in week_keys]
    key_index = {(k.year, k.week): i for i, k in enumerate(week_keys)}

    txs = db.execute(
        select(InventoryTransaction, PigmentLot, PigmentProduct)
        .join(PigmentLot, PigmentLot.id == InventoryTransaction.lot_id)
        .join(PigmentProduct, PigmentProduct.id == PigmentLot.product_id)
        .where(InventoryTransaction.tenant_id == t)
    ).all()

    rows: dict[str, dict] = {}
    for tx, _lot, product in txs:
        iso = tx.recorded_at.date().isocalendar()
        idx = key_index.get((iso.year, iso.week))
        if idx is None:
            continue
        row = rows.setdefault(product.id, {
            "code": product.internal_code,
            "product": product.product_name,
            "cells": [{"in_ml": 0.0, "out_ml": 0.0, "net_ml": 0.0} for _ in week_labels],
            "total_in_ml": 0.0,
            "total_out_ml": 0.0,
        })
        cell = row["cells"][idx]
        if tx.delta_ml >= 0:
            cell["in_ml"] = round(cell["in_ml"] + tx.delta_ml, 4)
            row["total_in_ml"] = round(row["total_in_ml"] + tx.delta_ml, 4)
        else:
            cell["out_ml"] = round(cell["out_ml"] - tx.delta_ml, 4)
            row["total_out_ml"] = round(row["total_out_ml"] - tx.delta_ml, 4)
        cell["net_ml"] = round(cell["in_ml"] - cell["out_ml"], 4)

    ordered = sorted(rows.values(), key=lambda r: r["total_in_ml"] + r["total_out_ml"], reverse=True)
    return {
        "pipeline": pipeline,
        "inventory_footprint": {"weeks": week_labels, "rows": ordered},
    }


@router.post("/pricing/estimate")
def pricing_estimate(body: EstimateIn, user: User = Depends(current_user)):
    """Configurable estimate (expansion spec) — studio inputs, no universal pricing claims."""
    area_component = max(
        body.minimum_fee, body.area_sq_in * body.area_rate_per_sq_in * body.complexity_factor
    )
    total = (
        body.consultation_fee + body.test_spot_fee + area_component
        + body.hours * body.hourly_rate + body.supplies + body.travel - body.discount
    )
    if body.area_sq_in < 1:
        tier = "micro"
    elif body.area_sq_in <= 4:
        tier = "small"
    elif body.area_sq_in <= 12:
        tier = "medium"
    elif body.area_sq_in <= 30:
        tier = "large"
    else:
        tier = "extra_large"
    return {
        "estimate": round(total, 2),
        "area_component": round(area_component, 2),
        "area_tier": tier,
    }


@router.post("/coverage/estimate")
def coverage_estimate(body: CoverageIn, user: User = Depends(current_user)):
    ml = coverage_estimate_ml(
        body.area_sq_cm, body.ml_per_sq_cm, body.passes, body.texture_factor, body.reserve_factor
    )
    return {"estimated_ml": ml}


@router.get("/formulas/{formula_id}/report.pdf")
def formula_report_pdf(formula_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """PDF session/formula report (spec section 4 MVP)."""
    from fpdf import FPDF

    f = tenant_get(db, Formula, formula_id, user.tenant_id, "formula")
    target = db.get(ColorMeasurement, f.target_measurement_id)
    ingredients = db.execute(
        select(FormulaIngredient).where(FormulaIngredient.formula_id == f.id)
    ).scalars().all()
    swatches = db.execute(select(Swatch).where(Swatch.formula_id == f.id)).scalars().all()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Skin Blend IQ - Formula Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 0, 0)
    pdf.multi_cell(0, 5,
        "Artist decision-support record. Not a medical diagnosis and not a guarantee of healed color. "
        "External swatch verification and artist approval are mandatory before any treatment.")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, f"Formula {f.id}  (v{f.version}, {f.status})", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    rows = [
        ("Purpose", f.purpose),
        ("Model version", f.model_version),
        ("Dataset version", f.dataset_version),
        ("Target L*a*b*", str(f.target_lab)),
        ("Predicted L*a*b*", str(f.predicted_lab)),
        ("Predicted dE2000", str(f.predicted_delta_e00)),
        ("Rounding dE added", str(f.rounding_delta_e)),
        ("Confidence", str(f.confidence)),
        ("Gamut status", f.gamut_status),
        ("Treatment grade", str(f.treatment_grade)),
        ("Illuminant / observer", f"{target.illuminant} / {target.observer}" if target else "-"),
        ("Uncertainty (dE)", str(target.delta_e_uncertainty) if target else "-"),
        ("Undertone", f"{target.undertone} ({target.undertone_confidence})" if target else "-"),
        ("ITA degrees", str(target.ita_degrees) if target else "-"),
    ]
    for k, v in rows:
        pdf.cell(60, 6, k)
        pdf.cell(0, 6, v, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, f"Recipe ({f.cap_total_drops} drops total)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for i in ingredients:
        lot = db.get(PigmentLot, i.pigment_lot_id)
        product = db.get(PigmentProduct, lot.product_id)
        pdf.cell(0, 6,
                 f"{i.code}: {i.drops} drops - {product.manufacturer} {product.product_name}, "
                 f"lot {lot.lot_number}, expiry {lot.expiry_date}",
                 new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "External swatch verification", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    if not swatches:
        pdf.cell(0, 6, "NOT PERFORMED - formula is not treatment-ready", new_x="LMARGIN", new_y="NEXT")
    for s in swatches:
        ms = db.execute(
            select(SwatchMeasurement).where(SwatchMeasurement.swatch_id == s.id)
        ).scalars().all()
        for m in ms:
            pdf.cell(0, 6,
                     f"Swatch {s.id[:8]} ({s.substrate}): dE2000 vs target = {m.delta_e00_vs_target}",
                     new_x="LMARGIN", new_y="NEXT")
        if not ms:
            pdf.cell(0, 6, f"Swatch {s.id[:8]} prepared, not yet measured", new_x="LMARGIN", new_y="NEXT")

    if f.warnings:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Warnings", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for w in f.warnings:
            pdf.multi_cell(0, 5, f"- {w}")

    data = bytes(pdf.output())
    audit.record(db, user.tenant_id, "report.generated", "formula", f.id, user.id)
    db.commit()
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="formula-{f.id[:8]}.pdf"'},
    )
