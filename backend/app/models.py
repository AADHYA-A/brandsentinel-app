from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base, EncryptedText


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


ROLES = ["Creator", "Authorised Reviewer", "Brand Manager", "Brand Admin"]
KINDS = ["glossary", "fact", "voice", "claims", "evidence", "sensitive", "visual"]


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    role: Mapped[str] = mapped_column(String(40))
    team: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str] = mapped_column(String(200), default="")


class KitRecord(Base):
    """One versioned record in the brand kit: glossary term, fact, voice clause, policy, evidence."""
    __tablename__ = "kit_records"
    __table_args__ = (UniqueConstraint("tenant_id", "rid", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    rid: Mapped[str] = mapped_column(String(60), index=True)       # citation id, e.g. G-01, F-104
    kind: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class KitChunk(Base):
    """Retrieval index over approved sources (grounded retrieval / RAG)."""
    __tablename__ = "kit_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    rid: Mapped[str] = mapped_column(String(60), index=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(JSON)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    team: Mapped[str] = mapped_column(String(80), default="")
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(EncryptedText, default="")
    source_type: Mapped[str] = mapped_column(String(20), default="text")  # text|html|docx|pdf|image
    filename: Mapped[str] = mapped_column(String(200), default="")
    local_only: Mapped[bool] = mapped_column(Boolean, default=False)
    alt_text: Mapped[str] = mapped_column(String(500), default="")
    image_path: Mapped[str] = mapped_column(String(300), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)          # blocks, image options, ocr flag
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")  # set when approved and locked
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    creator: Mapped["User"] = relationship(foreign_keys=[creator_id], lazy="joined")


class DocVersion(Base):
    __tablename__ = "doc_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(EncryptedText)
    note: Mapped[str] = mapped_column(String(300), default="")
    by_name: Mapped[str] = mapped_column(String(120))
    by_role: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ReviewRun(Base):
    __tablename__ = "review_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    text_hash: Mapped[str] = mapped_column(String(64))
    raw_count: Mapped[int] = mapped_column(Integer, default=0)
    kept_count: Mapped[int] = mapped_column(Integer, default=0)
    dropped: Mapped[list] = mapped_column(JSON, default=list)       # verifier rejections with reason
    ms: Mapped[int] = mapped_column(Integer, default=0)
    ai_status: Mapped[str] = mapped_column(String(60), default="not used")
    run_by: Mapped[str] = mapped_column(String(120), default="")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("review_runs.id"), index=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    key: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))               # High|Medium|Low|Cannot verify
    risk: Mapped[str] = mapped_column(String(10))
    method: Mapped[str] = mapped_column(String(12))                 # Rule|Heuristic|AI
    src: Mapped[str] = mapped_column(String(80))
    src_text: Mapped[str] = mapped_column(Text, default="")         # the cited clause, shown verbatim
    text: Mapped[str] = mapped_column(Text)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    why: Mapped[str] = mapped_column(Text)
    tip: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rep: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    block: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)   # disputed
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Decision(Base):
    """Creator decisions: the raw material for governance insights."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    team: Mapped[str] = mapped_column(String(80), default="")
    src: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40))
    finding_key: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(12))                   # accepted|edited|disputed
    reason: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    user_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditEvent(Base):
    """Append-only, hash-chained. There is no update or delete path in the API."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    doc_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class AIUsage(Base):
    """Exportable AI-use log (EU AI Act transparency). Stores metadata only, never content."""
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    doc_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    purpose: Mapped[str] = mapped_column(String(60))
    mode: Mapped[str] = mapped_column(String(40))      # llm | skipped: local-only | skipped: no key | error
    model: Mapped[str] = mapped_column(String(80), default="")
    input_chars: Mapped[int] = mapped_column(Integer, default=0)
    returned: Mapped[int] = mapped_column(Integer, default=0)
    kept: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String(300), default="")
