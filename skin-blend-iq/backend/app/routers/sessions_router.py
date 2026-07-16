from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user, require_role, tenant_get
from ..db import get_db
from ..models import (
    AdverseEvent,
    Batch,
    BodyZone,
    Case,
    ColorMeasurement,
    Consent,
    Formula,
    HealedFollowUp,
    TestSpot,
    TreatmentSession,
    User,
)
from ..serialize import to_dict

router = APIRouter(prefix="/v1", tags=["sessions"])


class TestSpotIn(BaseModel):
    case_id: str
    formula_id: str
    zone_id: str | None = None
    location_note: str | None = None
    size_mm: float | None = None
    technique: str | None = None
    follow_up_due: str | None = None


class TestSpotReviewIn(BaseModel):
    healed_review: dict  # too_light/too_dark/too_warm/... checklist
    approved: bool


class TestSpotOverrideIn(BaseModel):
    override_reason: str = Field(min_length=10)


class SessionIn(BaseModel):
    case_id: str
    formula_id: str
    batch_id: str | None = None
    zones: list[str] = []
    checklist: dict | None = None
    procedure: dict | None = None
    notes: str | None = None


class FollowUpIn(BaseModel):
    session_id: str
    interval_days: int | None = None
    measurement_id: str | None = None
    review: dict | None = None
    outcome: str | None = None


class FollowUpReviewIn(BaseModel):
    eligible_for_learning: bool
    outcome: str = Field(min_length=1)


class AdverseEventIn(BaseModel):
    case_id: str
    session_id: str | None = None
    symptoms: str = Field(min_length=3)
    detail: dict | None = None


def _require_treatment_consent(db: Session, tenant_id: str, case: Case):
    consent = db.execute(
        select(Consent)
        .where(
            Consent.client_id == case.client_id,
            Consent.tenant_id == tenant_id,
            Consent.kind == "treatment",
            Consent.granted == True,  # noqa: E712
        )
        .order_by(Consent.recorded_at.desc())
    ).scalars().first()
    if consent is None:
        raise HTTPException(status_code=409, detail="No current treatment consent on file for this client")


@router.post("/test-spots", status_code=201)
def create_test_spot(body: TestSpotIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = tenant_get(db, Case, body.case_id, user.tenant_id, "case")
    f = tenant_get(db, Formula, body.formula_id, user.tenant_id, "formula")
    _require_treatment_consent(db, user.tenant_id, case)
    if f.status not in ("locked", "used"):
        raise HTTPException(status_code=409, detail="Test spots require a locked formula")
    if not f.treatment_grade:
        raise HTTPException(
            status_code=403,
            detail="SAFETY BLOCK: this formula is not treatment-grade "
                   "(uncalibrated target or synthetic pigment data) and must never be applied to a person.",
        )
    if body.zone_id:
        tenant_get(db, BodyZone, body.zone_id, user.tenant_id, "zone")
    spot = TestSpot(tenant_id=user.tenant_id, **body.model_dump())
    db.add(spot)
    db.flush()
    case.status = "test_spot_healing"
    db.add(case)
    audit.record(db, user.tenant_id, "test_spot.created", "test_spot", spot.id, user.id,
                 {"formula_id": f.id})
    db.commit()
    return to_dict(spot)


@router.post("/test-spots/{spot_id}/review")
def review_test_spot(spot_id: str, body: TestSpotReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    spot = tenant_get(db, TestSpot, spot_id, user.tenant_id, "test spot")
    spot.healed_review = body.healed_review
    spot.approved = body.approved
    spot.status = "reviewed"
    spot.reviewed_by = user.id
    spot.reviewed_at = datetime.now(timezone.utc)
    db.add(spot)
    audit.record(db, user.tenant_id, "test_spot.reviewed", "test_spot", spot.id, user.id,
                 {"approved": body.approved, "review": body.healed_review})
    db.commit()
    return to_dict(spot)


@router.post("/treatment-sessions", status_code=201)
def create_treatment_session(body: SessionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = tenant_get(db, Case, body.case_id, user.tenant_id, "case")
    f = tenant_get(db, Formula, body.formula_id, user.tenant_id, "formula")
    _require_treatment_consent(db, user.tenant_id, case)
    if f.status not in ("locked", "used"):
        raise HTTPException(status_code=409, detail="Treatment requires a locked formula")
    if not f.treatment_grade:
        raise HTTPException(
            status_code=403,
            detail="SAFETY BLOCK: this formula is not treatment-grade "
                   "(uncalibrated target or synthetic pigment data) and must never be applied to a person.",
        )
    # Test-spot approval gates full treatment (expansion spec) unless overridden.
    if f.purpose == "full_session":
        approved_spot = db.execute(
            select(TestSpot).where(
                TestSpot.case_id == case.id,
                TestSpot.tenant_id == user.tenant_id,
                TestSpot.approved == True,  # noqa: E712
            )
        ).scalars().first()
        override = db.execute(
            select(TestSpot).where(
                TestSpot.case_id == case.id,
                TestSpot.tenant_id == user.tenant_id,
                TestSpot.override_reason.isnot(None),
            )
        ).scalars().first()
        if approved_spot is None and override is None:
            raise HTTPException(
                status_code=409,
                detail="Full treatment requires an approved test spot for this case "
                       "(or a documented override).",
            )
    if body.batch_id:
        batch = tenant_get(db, Batch, body.batch_id, user.tenant_id, "batch")
        if batch.formula_id != f.id:
            raise HTTPException(status_code=422, detail="Batch belongs to a different formula")
    session = TreatmentSession(
        tenant_id=user.tenant_id, artist_id=user.id, **body.model_dump(),
    )
    f.status = "used"
    case.status = "treatment_in_progress"
    db.add_all([session, f, case])
    db.flush()
    audit.record(db, user.tenant_id, "treatment.session_recorded", "treatment_session",
                 session.id, user.id, {"formula_id": f.id, "zones": body.zones})
    db.commit()
    return to_dict(session)


@router.post("/test-spots/{spot_id}/override", )
def override_test_spot_gate(
    spot_id: str, body: TestSpotOverrideIn,
    user: User = Depends(require_role("senior")), db: Session = Depends(get_db),
):
    """Documented senior override of the test-spot gate (expansion spec)."""
    spot = tenant_get(db, TestSpot, spot_id, user.tenant_id, "test spot")
    spot.override_reason = body.override_reason
    db.add(spot)
    audit.record(db, user.tenant_id, "test_spot.gate_overridden", "test_spot", spot.id, user.id,
                 {"reason": body.override_reason})
    db.commit()
    return to_dict(spot)


@router.post("/follow-ups", status_code=201)
def create_follow_up(body: FollowUpIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = tenant_get(db, TreatmentSession, body.session_id, user.tenant_id, "session")
    if body.measurement_id:
        tenant_get(db, ColorMeasurement, body.measurement_id, user.tenant_id, "measurement")
    fu = HealedFollowUp(tenant_id=user.tenant_id, **body.model_dump())
    db.add(fu)
    f = db.get(Formula, session.formula_id)
    if f and f.status == "used":
        f.status = "followup_pending"
        db.add(f)
    db.flush()
    audit.record(db, user.tenant_id, "followup.recorded", "healed_follow_up", fu.id, user.id)
    db.commit()
    return to_dict(fu)


@router.post("/follow-ups/{followup_id}/review")
def review_follow_up(
    followup_id: str, body: FollowUpReviewIn,
    user: User = Depends(require_role("senior")), db: Session = Depends(get_db),
):
    """Senior review; only reviewed, consented outcomes may enter the learning dataset."""
    fu = tenant_get(db, HealedFollowUp, followup_id, user.tenant_id, "follow-up")
    eligible = body.eligible_for_learning
    if eligible:
        session = db.get(TreatmentSession, fu.session_id)
        case = db.get(Case, session.case_id)
        consent = db.execute(
            select(Consent).where(
                Consent.client_id == case.client_id,
                Consent.tenant_id == user.tenant_id,
                Consent.kind == "ai_training",
                Consent.granted == True,  # noqa: E712
            )
        ).scalars().first()
        if consent is None:
            eligible = False  # No AI-training consent -> stays in the private client record.
    fu.eligible_for_learning = eligible
    fu.outcome = body.outcome
    fu.reviewed_by = user.id
    db.add(fu)
    session = db.get(TreatmentSession, fu.session_id)
    f = db.get(Formula, session.formula_id)
    if f and f.status == "followup_pending":
        f.status = "outcome_reviewed"
        db.add(f)
    audit.record(db, user.tenant_id, "followup.reviewed", "healed_follow_up", fu.id, user.id,
                 {"eligible_for_learning": eligible, "outcome": body.outcome})
    db.commit()
    out = to_dict(fu)
    if body.eligible_for_learning and not eligible:
        out["note"] = "Marked ineligible: client has no AI-training consent on file."
    return out


@router.post("/adverse-events", status_code=201)
def report_adverse_event(body: AdverseEventIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tenant_get(db, Case, body.case_id, user.tenant_id, "case")
    if body.session_id:
        tenant_get(db, TreatmentSession, body.session_id, user.tenant_id, "session")
    ev = AdverseEvent(tenant_id=user.tenant_id, reported_by=user.id, **body.model_dump())
    db.add(ev)
    db.flush()
    audit.record(db, user.tenant_id, "adverse_event.reported", "adverse_event", ev.id, user.id,
                 {"case_id": body.case_id})
    db.commit()
    return to_dict(ev)


@router.get("/cases/{case_id}/sessions")
def list_case_sessions(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tenant_get(db, Case, case_id, user.tenant_id, "case")
    sessions = db.execute(
        select(TreatmentSession).where(
            TreatmentSession.case_id == case_id, TreatmentSession.tenant_id == user.tenant_id
        )
    ).scalars().all()
    spots = db.execute(
        select(TestSpot).where(TestSpot.case_id == case_id, TestSpot.tenant_id == user.tenant_id)
    ).scalars().all()
    return {"sessions": [to_dict(s) for s in sessions], "test_spots": [to_dict(s) for s in spots]}
