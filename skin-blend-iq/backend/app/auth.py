"""Authentication, roles, and tenant scoping.

JWT bearer tokens; PBKDF2-SHA256 password hashing (stdlib, no external
crypto dependency). Every request resolves to (user, tenant) and all
queries filter by tenant_id — tenant isolation is enforced at the data
access layer, verified by tests.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import User

ROLE_RANK = {"trainee": 0, "artist": 1, "senior": 2, "owner": 3}

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _scheme, iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "tenant_id": user.tenant_id,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        payload = jwt.decode(
            auth.removeprefix("Bearer "),
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def require_role(minimum: str):
    def dep(user: User = Depends(current_user)) -> User:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[minimum]:
            raise HTTPException(status_code=403, detail=f"Requires {minimum} role")
        return user

    return dep


def tenant_get(db: Session, model, entity_id: str, tenant_id: str, name: str = "record"):
    """Fetch a tenant-owned row; 404s on cross-tenant access (no existence leak)."""
    row = db.get(model, entity_id)
    if row is None or getattr(row, "tenant_id", None) != tenant_id:
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return row
