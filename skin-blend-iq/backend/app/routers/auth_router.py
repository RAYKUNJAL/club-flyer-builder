from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import (
    create_token,
    current_user,
    hash_password,
    require_role,
    verify_password,
)
from ..db import get_db
from ..models import Tenant, User
from ..serialize import to_dict

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class RegisterStudio(BaseModel):
    studio_name: str = Field(min_length=1)
    name: str = Field(min_length=1)
    email: str
    password: str = Field(min_length=8)


class Login(BaseModel):
    email: str
    password: str


class CreateUser(BaseModel):
    name: str = Field(min_length=1)
    email: str
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(trainee|artist|senior|owner)$")


def _user_out(user: User) -> dict:
    return to_dict(user, exclude=("password_hash",))


@router.post("/register-studio", status_code=201)
def register_studio(body: RegisterStudio, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    tenant = Tenant(name=body.studio_name)
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=body.email,
        name=body.name,
        role="owner",
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    audit.record(db, tenant.id, "studio.registered", "tenant", tenant.id, user.id)
    db.commit()
    return {"token": create_token(user), "user": _user_out(user), "tenant": to_dict(tenant)}


@router.post("/login")
def login(body: Login, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    audit.record(db, user.tenant_id, "user.login", "user", user.id, user.id)
    db.commit()
    return {"token": create_token(user), "user": _user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _user_out(user)


@router.post("/users", status_code=201)
def create_user(
    body: CreateUser,
    user: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    if db.execute(select(User).where(User.email == body.email)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    new = User(
        tenant_id=user.tenant_id,
        email=body.email,
        name=body.name,
        role=body.role,
        password_hash=hash_password(body.password),
    )
    db.add(new)
    db.flush()
    audit.record(db, user.tenant_id, "user.created", "user", new.id, user.id, {"role": body.role})
    db.commit()
    return _user_out(new)


@router.post("/acknowledge")
def professional_acknowledgment(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Required professional acknowledgment: decision-support, not diagnosis."""
    user.professional_ack_at = datetime.now(timezone.utc)
    db.add(user)
    audit.record(db, user.tenant_id, "user.professional_ack", "user", user.id, user.id)
    db.commit()
    return _user_out(user)
