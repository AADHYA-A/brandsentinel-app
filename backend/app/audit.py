from __future__ import annotations
import hashlib
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .models import AuditEvent, now


def _h(prev: str, e: AuditEvent) -> str:
    s = "|".join([prev, str(e.seq), e.at.isoformat(), e.user_name, e.role, e.action, e.detail, str(e.doc_id)])
    return hashlib.sha256(s.encode()).hexdigest()


def log(db: Session, tenant_id: str, user_name: str, role: str, action: str, detail: str = "", doc_id=None) -> AuditEvent:
    last = db.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.seq.desc()).limit(1)).scalars().first()
    e = AuditEvent(tenant_id=tenant_id, seq=(last.seq + 1) if last else 1, at=now().replace(microsecond=0), user_name=user_name,
                   role=role, action=action, detail=detail[:2000], doc_id=doc_id, prev_hash=last.hash if last else "0" * 64, hash="")
    e.hash = _h(e.prev_hash, e)
    db.add(e)
    db.flush()
    return e


def verify_chain(db: Session, tenant_id: str) -> dict:
    rows = db.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.seq)).scalars().all()
    prev = "0" * 64
    for e in rows:
        if e.prev_hash != prev or e.hash != _h(prev, e):
            return {"ok": False, "events": len(rows), "broken_at": e.seq}
        prev = e.hash
    return {"ok": True, "events": len(rows), "broken_at": None}
