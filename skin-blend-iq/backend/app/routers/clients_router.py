from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user, tenant_get
from ..db import get_db
from ..models import BodyZone, Case, Client, Consent, User
from ..serialize import to_dict

router = APIRouter(prefix="/v1", tags=["clients"])

CONSENT_KINDS = {"treatment", "photography", "education", "marketing", "ai_training"}
CASE_TYPES = {
    "surgical_scar", "traumatic_scar", "burn_scar", "stretch_marks",
    "hypopigmentation", "vitiligo_camouflage", "areola_restoration",
    "cleft_lip_scar", "hair_transplant_scar", "scalp_scar",
    "skin_graft_boundary", "radiation_marker", "port_scar", "other",
}
CASE_STATUSES = {
    "inquiry", "pre_screening", "consultation_scheduled", "awaiting_medical_clearance",
    "not_currently_suitable", "test_spot_planned", "test_spot_healing",
    "formula_revision", "approved_for_treatment", "treatment_in_progress",
    "touch_up_pending", "completed", "annual_review", "referred_out",
}
ZONE_STATUSES = {"planned", "test_spot", "treated_this_session", "healed_approved", "needs_touch_up", "do_not_treat"}


class ClientIn(BaseModel):
    legal_name: str = Field(min_length=1)
    preferred_name: str | None = None
    date_of_birth: str | None = None
    email: str | None = None
    phone: str | None = None
    referral_source: str | None = None
    notes: str | None = None
    screening: dict | None = None


class ConsentIn(BaseModel):
    kind: str
    granted: bool


class CaseIn(BaseModel):
    client_id: str
    case_type: str
    notes: str | None = None


class CaseStatusIn(BaseModel):
    status: str


class ZoneIn(BaseModel):
    code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    view: str = "front"
    area_sq_cm: float | None = None
    notes: str | None = None


class ZoneStatusIn(BaseModel):
    status: str
    notes: str | None = None


@router.post("/clients", status_code=201)
def create_client(body: ClientIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    count = db.execute(
        select(func.count()).select_from(Client).where(Client.tenant_id == user.tenant_id)
    ).scalar_one()
    client = Client(
        tenant_id=user.tenant_id,
        display_code=f"SBI-C-{1000 + count + 1}",
        **body.model_dump(),
    )
    db.add(client)
    db.flush()
    audit.record(db, user.tenant_id, "client.created", "client", client.id, user.id)
    db.commit()
    return to_dict(client)


@router.get("/clients")
def list_clients(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Client).where(Client.tenant_id == user.tenant_id).order_by(Client.created_at.desc())
    ).scalars().all()
    return [to_dict(r) for r in rows]


@router.get("/clients/{client_id}")
def get_client(client_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = tenant_get(db, Client, client_id, user.tenant_id, "client")
    consents = db.execute(
        select(Consent).where(Consent.client_id == client.id, Consent.tenant_id == user.tenant_id)
    ).scalars().all()
    cases = db.execute(
        select(Case).where(Case.client_id == client.id, Case.tenant_id == user.tenant_id)
    ).scalars().all()
    out = to_dict(client)
    out["consents"] = [to_dict(c) for c in consents]
    out["cases"] = [to_dict(c) for c in cases]
    return out


@router.post("/clients/{client_id}/consents", status_code=201)
def record_consent(
    client_id: str, body: ConsentIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if body.kind not in CONSENT_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {sorted(CONSENT_KINDS)}")
    client = tenant_get(db, Client, client_id, user.tenant_id, "client")
    consent = Consent(
        tenant_id=user.tenant_id,
        client_id=client.id,
        kind=body.kind,
        granted=body.granted,
        recorded_by=user.id,
    )
    db.add(consent)
    db.flush()
    audit.record(
        db, user.tenant_id, "consent.recorded", "consent", consent.id, user.id,
        {"kind": body.kind, "granted": body.granted},
    )
    db.commit()
    return to_dict(consent)


@router.post("/cases", status_code=201)
def create_case(body: CaseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.case_type not in CASE_TYPES:
        raise HTTPException(status_code=422, detail=f"case_type must be one of {sorted(CASE_TYPES)}")
    tenant_get(db, Client, body.client_id, user.tenant_id, "client")
    case = Case(tenant_id=user.tenant_id, **body.model_dump())
    db.add(case)
    db.flush()
    audit.record(db, user.tenant_id, "case.created", "case", case.id, user.id)
    db.commit()
    return to_dict(case)


@router.get("/cases/{case_id}")
def get_case(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = tenant_get(db, Case, case_id, user.tenant_id, "case")
    zones = db.execute(
        select(BodyZone).where(BodyZone.case_id == case.id, BodyZone.tenant_id == user.tenant_id)
    ).scalars().all()
    out = to_dict(case)
    out["zones"] = [to_dict(z) for z in zones]
    return out


@router.post("/cases/{case_id}/status")
def set_case_status(
    case_id: str, body: CaseStatusIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if body.status not in CASE_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(CASE_STATUSES)}")
    case = tenant_get(db, Case, case_id, user.tenant_id, "case")
    old = case.status
    case.status = body.status
    db.add(case)
    audit.record(db, user.tenant_id, "case.status_changed", "case", case.id, user.id,
                 {"from": old, "to": body.status})
    db.commit()
    return to_dict(case)


@router.post("/cases/{case_id}/zones", status_code=201)
def create_zone(
    case_id: str, body: ZoneIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    case = tenant_get(db, Case, case_id, user.tenant_id, "case")
    zone = BodyZone(tenant_id=user.tenant_id, case_id=case.id, **body.model_dump())
    db.add(zone)
    db.flush()
    audit.record(db, user.tenant_id, "zone.created", "body_zone", zone.id, user.id,
                 {"code": body.code})
    db.commit()
    return to_dict(zone)


@router.post("/zones/{zone_id}/status")
def set_zone_status(
    zone_id: str, body: ZoneStatusIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if body.status not in ZONE_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(ZONE_STATUSES)}")
    zone = tenant_get(db, BodyZone, zone_id, user.tenant_id, "zone")
    old = zone.status
    zone.status = body.status
    if body.notes:
        zone.notes = body.notes
    db.add(zone)
    audit.record(db, user.tenant_id, "zone.status_changed", "body_zone", zone.id, user.id,
                 {"from": old, "to": body.status})
    db.commit()
    return to_dict(zone)
