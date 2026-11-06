"""Document workflow and finding decisions. All state changes go through here and are audited."""
from __future__ import annotations
import difflib
import re
from datetime import date
from typing import Optional
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from . import audit
from .models import Comment, Decision, DocVersion, Document, Finding, User, now
from .pipeline import current_findings, review_is_fresh, run_review, sha

EDITABLE = ("draft", "changes_requested")
LABEL = {"draft": "Draft", "pending_reviewer": "Waiting for Authorised Reviewer", "pending_manager": "Waiting for Brand Manager",
         "approved": "Approved for publication", "changes_requested": "Changes requested", "published": "Published"}
MAX_TEXT = 200_000


def get_doc(db: Session, user: User, doc_id: int) -> Document:
    d = db.get(Document, doc_id)
    if not d or d.tenant_id != user.tenant_id:          # tenant isolation
        raise HTTPException(404, "Document not found.")
    if user.role == "Creator" and d.creator_id != user.id:
        raise HTTPException(404, "Document not found.")
    if user.role == "Authorised Reviewer" and d.status not in ("pending_reviewer", "pending_manager", "approved", "published"):
        raise HTTPException(403, "Reviewers see documents only once they are routed for review.")
    return d


def perms(user: User, d: Document, open_count: int, fresh: bool) -> dict:
    own = user.role == "Creator" and d.creator_id == user.id
    return {"edit": own and d.status in EDITABLE, "decide": own and d.status in EDITABLE,
            "submit": own and d.status in EDITABLE and fresh and open_count == 0 and bool(d.text.strip() or d.source_type == "image"),
            "reviewer": user.role == "Authorised Reviewer" and d.status == "pending_reviewer",
            "manager": user.role == "Brand Manager" and d.status == "pending_manager" and d.creator_id != user.id,
            "publish": user.role == "Brand Manager" and d.status == "approved",
            "new_revision": own and d.status == "approved"}


def _need_edit(user: User, d: Document):
    if user.role != "Creator" or d.creator_id != user.id:
        raise HTTPException(403, "Only the Creator can change this draft.")
    if d.status not in EDITABLE:
        raise HTTPException(409, "This draft is locked while it is in review or approved.")


def create_doc(db: Session, user: User, title: str, text: str, team: str, local_only: bool, source_type="text", filename="",
               blocks=None, meta=None) -> Document:
    if len(text) > MAX_TEXT:
        raise HTTPException(413, "Text is too long (200,000 characters maximum).")
    m = dict(meta or {})
    if blocks:
        m["blocks"] = blocks
    d = Document(tenant_id=user.tenant_id, title=(title or filename or "Untitled draft")[:200], team=team or user.team, creator_id=user.id,
                 text=text, source_type=source_type, filename=filename, local_only=local_only, meta=m)
    db.add(d)
    db.flush()
    audit.log(db, user.tenant_id, user.name, user.role, "Draft created", f"{d.title} ({source_type})", d.id)
    return d


def set_text(db: Session, user: User, d: Document, text: str):
    _need_edit(user, d)
    if d.source_type in ("docx", "pdf", "image"):
        raise HTTPException(400, "Uploaded documents are reviewed as extracted; upload a corrected file instead.")
    if len(text) > MAX_TEXT:
        raise HTTPException(413, "Text is too long.")
    d.text = text.replace("\x00", "")
    d.meta = {k: v for k, v in d.meta.items() if k != "blocks"}
    audit.log(db, user.tenant_id, user.name, user.role, "Draft edited", f"{len(text)} characters", d.id)


def _fresh_run(db: Session, d: Document):
    run, fs = current_findings(db, d)
    if not review_is_fresh(d, run):
        raise HTTPException(409, "The draft changed since the last review. Run the review again first.")
    return run, fs


def _find(fs, fid: int) -> Finding:
    f = next((x for x in fs if x.id == fid), None)
    if not f:
        raise HTTPException(404, "Finding not found in the current review.")
    return f


def _record(db: Session, user: User, d: Document, f: Finding, kind: str, reason: str = ""):
    db.execute(delete(Decision).where(Decision.doc_id == d.id, Decision.finding_key == f.key, Decision.kind == "disputed"))
    db.add(Decision(tenant_id=d.tenant_id, doc_id=d.id, team=d.team, src=f.src, category=f.category, finding_key=f.key, kind=kind,
                    reason=reason, user_id=user.id))


def decide(db: Session, user: User, d: Document, fid: int, action: str, text: str = "", reason: str = "") -> None:
    _need_edit(user, d)
    run, fs = _fresh_run(db, d)
    f = _find(fs, fid)
    if action in ("accept", "edit"):
        if d.source_type in ("image", "docx", "pdf"):
            raise HTTPException(400, "Fixes cannot be applied to this file type. Correct the source and upload it again.")
        if action == "accept":
            if f.rep is None:
                raise HTTPException(400, "This finding has no suggested fix. Edit the text or dispute it.")
            new = f.rep
        else:
            new = text
            if new == f.text:
                raise HTTPException(400, "Change the text first.")
        if d.text[f.start:f.end] != f.text:
            raise HTTPException(409, "The draft no longer matches this finding. Run the review again.")
        d.text = d.text[:f.start] + new + d.text[f.end:]
        d.meta = {k: v for k, v in d.meta.items() if k != "blocks"}
        _record(db, user, d, f, "accepted" if action == "accept" else "edited")
        audit.log(db, d.tenant_id, user.name, user.role, "Accepted fix" if action == "accept" else "Edited text",
                  f"{f.src}: “{f.text}” → “{new}”", d.id)
        run_review(db, d, user)          # re-check, which also confirms the fix did not introduce a new issue
    elif action == "dispute":
        if not reason.strip():
            raise HTTPException(400, "A reason is required to dispute a finding.")
        f.decision, f.reason = "disputed", reason.strip()
        _record(db, user, d, f, "disputed", reason.strip())
        audit.log(db, d.tenant_id, user.name, user.role, "Disputed finding", f"{f.src} “{f.text}”: {reason.strip()}", d.id)
    elif action == "undo":
        db.execute(delete(Decision).where(Decision.doc_id == d.id, Decision.finding_key == f.key, Decision.kind == "disputed"))
        f.decision = f.reason = None
        audit.log(db, d.tenant_id, user.name, user.role, "Dispute withdrawn", f.src, d.id)
    else:
        raise HTTPException(400, "Unknown action.")


def submit(db: Session, user: User, d: Document) -> str:
    _need_edit(user, d)
    run, fs = current_findings(db, d)
    if not review_is_fresh(d, run):
        raise HTTPException(409, "Run a review on the current draft first.")
    open_n = sum(1 for f in fs if not f.decision)
    if open_n:
        raise HTTPException(409, f"Decide on {open_n} open finding{'s' if open_n > 1 else ''} first.")
    d.version += 1
    disputed = [f for f in fs if f.decision]
    to_reviewer = any(f.risk == "high" for f in fs)   # a high-risk claim is still in the text: needs a human with authority
    fixes = db.execute(select(Decision).where(Decision.doc_id == d.id, Decision.kind.in_(["accepted", "edited"]))).scalars().all()
    db.add(DocVersion(doc_id=d.id, version=d.version, text=d.text, by_name=user.name, by_role=user.role,
                      note=f"{len(fixes)} fixes applied in total, {len(disputed)} disputed"))
    d.status = "pending_reviewer" if to_reviewer else "pending_manager"
    d.submitted_at = d.submitted_at or now()
    audit.log(db, d.tenant_id, user.name, user.role, "Submitted",
              f"Version {d.version}, routed to {'Authorised Reviewer (high-risk claim still in text)' if to_reviewer else 'Brand Manager'}", d.id)
    return d.status


def comment(db: Session, user: User, d: Document, text: str):
    text = text.strip()
    if not text:
        raise HTTPException(400, "Write a comment first.")
    db.add(Comment(doc_id=d.id, user_name=user.name, role=user.role, text=text[:2000]))
    audit.log(db, d.tenant_id, user.name, user.role, "Comment", text[:300], d.id)


def reviewer_clear(db: Session, user: User, d: Document, note: str):
    if d.status != "pending_reviewer" or user.role != "Authorised Reviewer":
        raise HTTPException(409, "Nothing for you to clear on this document.")
    d.status = "pending_manager"
    db.add(Comment(doc_id=d.id, user_name=user.name, role=user.role, text=note.strip() or "Cleared."))
    audit.log(db, d.tenant_id, user.name, user.role, "Reviewer cleared high-risk items", note[:300], d.id)


def request_changes(db: Session, user: User, d: Document, note: str):
    ok = (d.status == "pending_reviewer" and user.role == "Authorised Reviewer") or (d.status == "pending_manager" and user.role == "Brand Manager")
    if not ok:
        raise HTTPException(409, "You cannot request changes at this stage.")
    if not note.strip():
        raise HTTPException(400, "A note is required to request changes.")
    d.status = "changes_requested"
    db.add(Comment(doc_id=d.id, user_name=user.name, role=user.role, text=note.strip()))
    audit.log(db, d.tenant_id, user.name, user.role, "Changes requested", note[:300], d.id)


def approve(db: Session, user: User, d: Document, note: str):
    if d.status != "pending_manager" or user.role != "Brand Manager":
        raise HTTPException(409, "This document is not waiting for your approval.")
    if d.creator_id == user.id:
        raise HTTPException(403, "You cannot approve your own draft.")
    d.status, d.approved_at, d.content_hash = "approved", now(), sha(d.text + "|" + d.alt_text)
    db.add(Comment(doc_id=d.id, user_name=user.name, role=user.role, text=note.strip() or "Approved."))
    audit.log(db, d.tenant_id, user.name, user.role, "Approved for publication", f"Version {d.version}, locked, sha256 {d.content_hash[:12]}", d.id)


def publish(db: Session, user: User, d: Document):
    if d.status != "approved" or user.role != "Brand Manager":
        raise HTTPException(409, "Only an approved document can be published, by a Brand Manager.")
    d.status = "published"
    audit.log(db, d.tenant_id, user.name, user.role, "Published", f"Version {d.version}, sha256 {d.content_hash[:12]}", d.id)


def new_revision(db: Session, user: User, d: Document):
    if user.role != "Creator" or d.creator_id != user.id or d.status != "approved":
        raise HTTPException(409, "Only the Creator can start a revision of an approved draft.")
    d.status, d.approved_at, d.content_hash = "draft", None, ""
    audit.log(db, d.tenant_id, user.name, user.role, "New revision started", "", d.id)


def diff(db: Session, d: Document, a: int, b: Optional[int]) -> list[dict]:
    def txt(v):
        if v is None:
            return d.text
        row = db.execute(select(DocVersion).where(DocVersion.doc_id == d.id, DocVersion.version == v)).scalars().first()
        if not row:
            raise HTTPException(404, f"Version {v} not found.")
        return row.text
    x, y = txt(a), txt(b)
    tok = lambda s: re.findall(r"\s+|\S+", s)
    tx, ty = tok(x), tok(y)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, tx, ty, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": "".join(tx[i1:i2])})
        else:
            if i2 > i1:
                out.append({"op": "delete", "text": "".join(tx[i1:i2])})
            if j2 > j1:
                out.append({"op": "insert", "text": "".join(ty[j1:j2])})
    return out
