"""Skin Blend IQ data model (spec sections 15 and expansion entities).

UUID string primary keys throughout; JSON columns hold structured
sub-records (quality scores, patch geometry, review checklists) that
have no relational consumers yet. All tenant-owned rows carry tenant_id
and every access path filters on it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="artist")  # owner|senior|artist|trainee
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    professional_ack_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    display_code: Mapped[str] = mapped_column(String, nullable=False)  # e.g. SBI-C-1048
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String)
    date_of_birth: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    referral_source: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    screening: Mapped[dict | None] = mapped_column(JSON)  # intake questionnaire answers
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    # treatment|photography|education|marketing|ai_training — always separate.
    kind: Mapped[str] = mapped_column(String, nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    case_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="inquiry")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BodyZone(Base):
    __tablename__ = "body_zones"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)  # e.g. V01
    label: Mapped[str] = mapped_column(String, nullable=False)
    view: Mapped[str] = mapped_column(String, default="front")
    area_sq_cm: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="planned")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReferenceCard(Base):
    __tablename__ = "reference_cards"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # [{"name": "N5 gray", "lab": [L, a, b]}, ...]
    patches: Mapped[list] = mapped_column(JSON, nullable=False)


class CaptureSession(Base):
    __tablename__ = "capture_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("body_zones.id"))
    mode: Mapped[str] = mapped_column(String, default="calibrated")  # quick|calibrated|instrument
    reference_card_id: Mapped[str | None] = mapped_column(ForeignKey("reference_cards.id"))
    status: Mapped[str] = mapped_column(String, default="open")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ImageAsset(Base):
    __tablename__ = "image_assets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    capture_id: Mapped[str] = mapped_column(ForeignKey("capture_sessions.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    stored_path: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    quality: Mapped[dict | None] = mapped_column(JSON)  # section 6 scores
    grade: Mapped[str | None] = mapped_column(String)   # pass|marginal|fail
    card_patches: Mapped[list | None] = mapped_column(JSON)  # marked card patch rects
    correction_matrix: Mapped[list | None] = mapped_column(JSON)
    correction_residual: Mapped[float | None] = mapped_column(Float)
    correction_passed: Mapped[bool | None] = mapped_column(Boolean)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SkinPatch(Base):
    __tablename__ = "skin_patches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    image_id: Mapped[str] = mapped_column(ForeignKey("image_assets.id"), nullable=False)
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)  # {x,y,w,h}
    pixel_count: Mapped[int | None] = mapped_column(Integer)
    median_rgb: Mapped[list | None] = mapped_column(JSON)
    corrected_rgb: Mapped[list | None] = mapped_column(JSON)
    lab: Mapped[list | None] = mapped_column(JSON)
    spread: Mapped[float | None] = mapped_column(Float)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    reject_reason: Mapped[str | None] = mapped_column(String)


class ColorMeasurement(Base):
    __tablename__ = "color_measurements"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    capture_id: Mapped[str | None] = mapped_column(ForeignKey("capture_sessions.id"))
    source_type: Mapped[str] = mapped_column(String, nullable=False)  # capture|swatch|instrument|manual
    lab_l: Mapped[float] = mapped_column(Float, nullable=False)
    lab_a: Mapped[float] = mapped_column(Float, nullable=False)
    lab_b: Mapped[float] = mapped_column(Float, nullable=False)
    rgb_display: Mapped[list | None] = mapped_column(JSON)
    hsv: Mapped[list | None] = mapped_column(JSON)
    ita_degrees: Mapped[float | None] = mapped_column(Float)
    undertone: Mapped[str | None] = mapped_column(String)
    undertone_confidence: Mapped[float | None] = mapped_column(Float)
    illuminant: Mapped[str] = mapped_column(String, default="D65")
    observer: Mapped[str] = mapped_column(String, default="2deg")
    delta_e_uncertainty: Mapped[float | None] = mapped_column(Float)
    treatment_grade: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[dict | None] = mapped_column(JSON)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PigmentProduct(Base):
    __tablename__ = "pigment_products"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String, nullable=False)
    brand_line: Mapped[str | None] = mapped_column(String)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    internal_code: Mapped[str] = mapped_column(String, nullable=False)  # e.g. P-Y
    color_role: Mapped[str] = mapped_column(String, nullable=False)
    regulatory_region: Mapped[str] = mapped_column(String, default="US")
    spectral_data_available: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="active")


class PigmentLot(Base):
    __tablename__ = "pigment_lots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("pigment_products.id"), nullable=False)
    lot_number: Mapped[str] = mapped_column(String, nullable=False)
    expiry_date: Mapped[str] = mapped_column(String, nullable=False)  # ISO date
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    sterility_status: Mapped[str] = mapped_column(String, default="active")
    status: Mapped[str] = mapped_column(String, default="active")  # active|quarantined|recalled|depleted
    quantity_ml: Mapped[float] = mapped_column(Float, default=15.0)


class DropperCalibration(Base):
    __tablename__ = "dropper_calibrations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("pigment_products.id"))
    drop_volume_ml_mean: Mapped[float] = mapped_column(Float, nullable=False)
    drop_volume_ml_std: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tolerance_pct: Mapped[float] = mapped_column(Float, default=10.0)
    within_tolerance: Mapped[bool] = mapped_column(Boolean, default=True)
    operator: Mapped[str | None] = mapped_column(String)
    calibrated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PigmentKit(Base):
    __tablename__ = "pigment_kits"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String, nullable=False)
    data_source: Mapped[str] = mapped_column(String, default="measured")  # measured|synthetic
    status: Mapped[str] = mapped_column(String, default="active")


class KitPigment(Base):
    __tablename__ = "kit_pigments"
    kit_id: Mapped[str] = mapped_column(ForeignKey("pigment_kits.id"), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("pigment_products.id"), primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)


class MixtureSampleRow(Base):
    __tablename__ = "mixture_samples"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    kit_id: Mapped[str] = mapped_column(ForeignKey("pigment_kits.id"), nullable=False)
    ratios: Mapped[dict] = mapped_column(JSON, nullable=False)
    lab: Mapped[list] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String, default="measured")
    recorded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Formula(Base):
    __tablename__ = "formulas"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_formula_id: Mapped[str | None] = mapped_column(ForeignKey("formulas.id"))
    purpose: Mapped[str] = mapped_column(String, default="full_session")  # test_spot|full_session|touch_up
    target_measurement_id: Mapped[str] = mapped_column(ForeignKey("color_measurements.id"), nullable=False)
    pigment_kit_id: Mapped[str] = mapped_column(ForeignKey("pigment_kits.id"), nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String, nullable=False)
    cap_total_drops: Mapped[int] = mapped_column(Integer, nullable=False)
    continuous_ratios: Mapped[dict] = mapped_column(JSON, nullable=False)
    target_lab: Mapped[list] = mapped_column(JSON, nullable=False)
    predicted_lab: Mapped[list | None] = mapped_column(JSON)
    predicted_delta_e00: Mapped[float | None] = mapped_column(Float)
    predicted_delta_e76: Mapped[float | None] = mapped_column(Float)
    rounding_delta_e: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    gamut_status: Mapped[str] = mapped_column(String, nullable=False)
    treatment_grade: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="draft")
    warnings: Mapped[list | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)


class FormulaIngredient(Base):
    __tablename__ = "formula_ingredients"
    formula_id: Mapped[str] = mapped_column(ForeignKey("formulas.id"), primary_key=True)
    pigment_lot_id: Mapped[str] = mapped_column(ForeignKey("pigment_lots.id"), primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    drops: Mapped[int] = mapped_column(Integer, nullable=False)


class FormulaAdjustment(Base):
    __tablename__ = "formula_adjustments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    formula_id: Mapped[str] = mapped_column(ForeignKey("formulas.id"), nullable=False)
    before_drops: Mapped[dict] = mapped_column(JSON, nullable=False)
    after_drops: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    adjusted_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    adjusted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Swatch(Base):
    __tablename__ = "swatches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    formula_id: Mapped[str] = mapped_column(ForeignKey("formulas.id"), nullable=False)
    substrate: Mapped[str] = mapped_column(String, default="practice-skin")
    prepared_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    prepared_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String, default="prepared")  # prepared|measured


class SwatchMeasurement(Base):
    __tablename__ = "swatch_measurements"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    swatch_id: Mapped[str] = mapped_column(ForeignKey("swatches.id"), nullable=False)
    measurement_id: Mapped[str] = mapped_column(ForeignKey("color_measurements.id"), nullable=False)
    delta_e00_vs_target: Mapped[float] = mapped_column(Float, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    formula_id: Mapped[str] = mapped_column(ForeignKey("formulas.id"), nullable=False)
    display_code: Mapped[str] = mapped_column(String, nullable=False)  # SBI-B-xxxx
    total_ml: Mapped[float] = mapped_column(Float, nullable=False)
    ingredients_ml: Mapped[dict] = mapped_column(JSON, nullable=False)
    rounding_differences_ml: Mapped[dict | None] = mapped_column(JSON)
    planned_zones: Mapped[list | None] = mapped_column(JSON)
    prepared_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    prepared_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    quantity_used_ml: Mapped[float | None] = mapped_column(Float)
    quantity_discarded_ml: Mapped[float | None] = mapped_column(Float)
    label_text: Mapped[str | None] = mapped_column(Text)


class TestSpot(Base):
    __tablename__ = "test_spots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    formula_id: Mapped[str] = mapped_column(ForeignKey("formulas.id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("body_zones.id"))
    location_note: Mapped[str | None] = mapped_column(String)
    size_mm: Mapped[float | None] = mapped_column(Float)
    technique: Mapped[str | None] = mapped_column(String)
    performed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    follow_up_due: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="healing")  # healing|reviewed
    healed_review: Mapped[dict | None] = mapped_column(JSON)
    approved: Mapped[bool | None] = mapped_column(Boolean)
    override_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)


class TreatmentSession(Base):
    __tablename__ = "treatment_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    formula_id: Mapped[str] = mapped_column(ForeignKey("formulas.id"), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"))
    artist_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    zones: Mapped[list | None] = mapped_column(JSON)
    checklist: Mapped[dict | None] = mapped_column(JSON)
    procedure: Mapped[dict | None] = mapped_column(JSON)
    performed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text)


class HealedFollowUp(Base):
    __tablename__ = "healed_follow_ups"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("treatment_sessions.id"), nullable=False)
    measurement_id: Mapped[str | None] = mapped_column(ForeignKey("color_measurements.id"))
    interval_days: Mapped[int | None] = mapped_column(Integer)
    review: Mapped[dict | None] = mapped_column(JSON)
    outcome: Mapped[str | None] = mapped_column(String)
    eligible_for_learning: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    lot_id: Mapped[str] = mapped_column(ForeignKey("pigment_lots.id"), nullable=False)
    delta_ml: Mapped[float] = mapped_column(Float, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # receive|use|discard|adjust
    note: Mapped[str | None] = mapped_column(String)
    recorded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Recall(Base):
    __tablename__ = "recalls"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    lot_id: Mapped[str] = mapped_column(ForeignKey("pigment_lots.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdverseEvent(Base):
    __tablename__ = "adverse_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("treatment_sessions.id"))
    symptoms: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON)
    reported_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String)
    payload: Mapped[dict | None] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "seq", name="uq_audit_tenant_seq"),)
