"""Immutable audit-event pipeline (spec sections 15, 17, 18).

Events form a per-tenant hash chain: each event's hash covers its
content plus the previous event's hash, so any tampering or deletion
breaks verification. The API exposes read and verify only — there is no
update or delete path for audit rows.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AuditEvent

GENESIS_HASH = "0" * 64


def _canon_ts(dt: datetime) -> str:
    """Canonical timestamp string: naive UTC. SQLite drops tzinfo on
    round-trip, so hashing must not depend on it."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat()


def _event_hash(
    tenant_id: str,
    seq: int,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict | None,
    created_at: str,
    prev_hash: str,
) -> str:
    body = json.dumps(
        {
            "tenant_id": tenant_id,
            "seq": seq,
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "created_at": created_at,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode()).hexdigest()


def record(
    db: Session,
    tenant_id: str,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor_id: str | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    last = db.execute(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.seq.desc())
        .limit(1)
    ).scalar_one_or_none()
    seq = (last.seq + 1) if last else 1
    prev_hash = last.hash if last else GENESIS_HASH
    created_at = datetime.now(timezone.utc)
    ev = AuditEvent(
        tenant_id=tenant_id,
        seq=seq,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        prev_hash=prev_hash,
        hash=_event_hash(
            tenant_id,
            seq,
            actor_id,
            action,
            entity_type,
            entity_id,
            payload,
            _canon_ts(created_at),
            prev_hash,
        ),
        created_at=created_at,
    )
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session, tenant_id: str) -> dict:
    events = (
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.seq)
        )
        .scalars()
        .all()
    )
    prev = GENESIS_HASH
    for ev in events:
        expected = _event_hash(
            ev.tenant_id,
            ev.seq,
            ev.actor_id,
            ev.action,
            ev.entity_type,
            ev.entity_id,
            ev.payload,
            _canon_ts(ev.created_at),
            prev,
        )
        if ev.prev_hash != prev or ev.hash != expected:
            return {"valid": False, "broken_at_seq": ev.seq, "count": len(events)}
        prev = ev.hash
    return {"valid": True, "count": len(events)}
