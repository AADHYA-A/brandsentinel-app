from __future__ import annotations
import csv
import io
import json
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from . import audit, insights, services as svc, storage
from .ai import get_provider
from .config import settings
from .db import get_db
from .evalset import evaluate
from .kit import SYSTEM_SOURCES, Rec, load_kit, parse_any, parse_date, save_record, render_record
from .models import AIUsage, AuditEvent, Comment, DocVersion, Document, Finding, KitRecord, User
from .parser import IMG_EXT, parse_bytes, sanitise
from .pipeline import current_findings, review_is_fresh, run_review
from .retrieval import index_kit
from .security import check_pw, current_user, make_token, rate_limit, require

r = APIRouter(prefix="/api")


# ---------- auth ----------
class LoginIn(BaseModel):
    email: str
    password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "team": u.team, "tenant": u.tenant_id}


@r.post("/auth/login")
def login(b: LoginIn, db: Session = Depends(get_db)):
    if not settings.dev_login:
        raise HTTPException(404, "Password login is disabled; use your identity provider.")
    u = db.execute(select(User).where(User.email == b.email.strip().lower())).scalars().first()
    if not u or not check_pw(b.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password.")
    return {"token": make_token(u), "user": user_out(u)}


@r.get("/auth/demo-users")
def demo_users(db: Session = Depends(get_db)):
    if not (settings.dev_login and settings.seed_demo):
        return []
    return [dict(user_out(u), password=settings.demo_password) for u in db.execute(select(User).order_by(User.id)).scalars()]


@r.get("/auth/me")
def me(u: User = Depends(current_user)):
    return user_out(u)


@r.get("/disclosure")
def disclosure(u: User = Depends(current_user)):
    ai = bool(get_provider()) and not settings.tenant_local_only
    return {"ai_configured": ai, "model": settings.llm_model if ai else None, "tenant_local_only": settings.tenant_local_only,
            "text": ("Findings are labelled Rule (deterministic), Heuristic (rule-based) or AI (model, grounded in retrieved approved sources and "
                     "re-checked by the verifier). " + ("An external model is configured for non-confidential, non-local-only drafts. "
                     "Draft content is sent only for the review request, is not stored by this system outside your tenant, and is never used for model training by design."
                     if ai else "No AI model is configured in this deployment, so every check is deterministic or rule-based.")),
            "storage": "Draft text and uploaded files are encrypted at rest. Local-only drafts never leave this server."}


# ---------- documents ----------
def finding_out(f: Finding) -> dict:
    return {"id": f.id, "key": f.key, "category": f.category, "severity": f.severity, "risk": f.risk, "method": f.method, "src": f.src,
            "src_text": f.src_text, "text": f.text, "start": f.start, "end": f.end, "why": f.why, "tip": f.tip, "rep": f.rep,
            "confidence": f.confidence, "block": f.block, "decision": f.decision, "reason": f.reason}


def summary(db: Session, d: Document) -> dict:
    run, fs = current_findings(db, d)
    return {"id": d.id, "title": d.title, "team": d.team, "status": d.status, "status_label": svc.LABEL[d.status], "version": d.version,
            "source_type": d.source_type, "creator": d.creator.name, "local_only": d.local_only,
            "high_risk": sum(1 for f in fs if f.risk == "high"), "finding_count": len(fs), "open": sum(1 for f in fs if not f.decision),
            "submitted_at": d.submitted_at.isoformat() if d.submitted_at else None, "updated_at": d.updated_at.isoformat()}


def full(db: Session, u: User, d: Document) -> dict:
    run, fs = current_findings(db, d)
    fresh = review_is_fresh(d, run)
    open_n = sum(1 for f in fs if not f.decision)
    out = summary(db, d)
    out.update({
        "text": d.text, "filename": d.filename, "alt_text": d.alt_text, "blocks": d.meta.get("blocks", []), "image_stats": d.meta.get("image_stats"),
        "notes": d.meta.get("notes", []), "reviewed": run is not None, "fresh": fresh,
        "run": {"id": run.id, "at": run.at.isoformat(), "raw": run.raw_count, "kept": run.kept_count, "dropped": run.dropped, "ms": run.ms,
                "ai_status": run.ai_status} if run else None,
        "findings": [finding_out(f) for f in fs] if fresh else [],
        "perms": svc.perms(u, d, open_n, fresh),
        "comments": [{"user": c.user_name, "role": c.role, "text": c.text, "at": c.at.isoformat()} for c in
                     db.execute(select(Comment).where(Comment.doc_id == d.id).order_by(Comment.id)).scalars()],
        "versions": [{"version": v.version, "at": v.at.isoformat(), "by": v.by_name, "role": v.by_role, "note": v.note, "text": v.text} for v in
                     db.execute(select(DocVersion).where(DocVersion.doc_id == d.id).order_by(DocVersion.version)).scalars()],
    })
    if u.role == "Authorised Reviewer":      # reviewers see only what needs expertise
        out["findings"] = [f for f in out["findings"] if f["risk"] == "high"]
    return out


class DocIn(BaseModel):
    title: str = Field("", max_length=200)
    text: str = ""
    team: str = Field("", max_length=80)
    local_only: bool = False


@r.post("/documents")
def create_document(b: DocIn, u: User = Depends(require("Creator")), db: Session = Depends(get_db)):
    d = svc.create_doc(db, u, b.title, sanitise(b.text), b.team, b.local_only)
    db.commit()
    return full(db, u, d)


@r.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), title: str = Form(""), team: str = Form(""), local_only: bool = Form(False),
                          alt_text: str = Form(""), text_colour: str = Form(""), bg_colour: str = Form(""),
                          u: User = Depends(require("Creator")), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")
    name = (file.filename or "upload").replace("/", "_")[:150]
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    try:
        if ext in IMG_EXT:
            from PIL import Image
            import io as _io
            try:
                Image.open(_io.BytesIO(data)).verify()
            except Exception:
                raise ValueError("This file is not a readable image.")
            path = storage.save(data, ext, u.tenant_id)
            d = svc.create_doc(db, u, title or name, "", team, local_only, "image", name, meta={"image_opts": {
                "text_colour": text_colour.strip() or None, "bg_colour": bg_colour.strip() or None}})
            d.image_path, d.alt_text = path, alt_text.strip()
        else:
            p = parse_bytes(name, data)
            d = svc.create_doc(db, u, title or name, p.text, team, local_only, p.source_type, name, p.blocks, {"notes": p.notes})
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return full(db, u, d)


@r.get("/documents/{doc_id}/image")
def doc_image(doc_id: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    d = svc.get_doc(db, u, doc_id)
    if d.source_type != "image":
        raise HTTPException(404, "Not an image document.")
    ext = d.filename.rsplit(".", 1)[-1].lower()
    return Response(storage.read(d.image_path), media_type={"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}.get(ext, "application/octet-stream"),
                    headers={"Cache-Control": "private, no-store", "Content-Security-Policy": "default-src 'none'"})


@r.get("/documents")
def list_documents(status: Optional[str] = None, u: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Document).where(Document.tenant_id == u.tenant_id)
    if u.role == "Creator":
        q = q.where(Document.creator_id == u.id)
    elif u.role == "Authorised Reviewer":
        q = q.where(Document.status.in_(["pending_reviewer", "pending_manager", "approved", "published"]))
    if status:
        q = q.where(Document.status == status)
    rows = [summary(db, d) for d in db.execute(q.order_by(Document.updated_at.desc())).scalars()]
    waiting = {"Authorised Reviewer": "pending_reviewer", "Brand Manager": "pending_manager"}.get(u.role)
    for x in rows:   # review queue prioritised by risk: waiting-for-me first, then high-risk items, then oldest
        x["mine_to_review"] = x["status"] == waiting
    rows.sort(key=lambda x: (not x["mine_to_review"], -x["high_risk"], x["submitted_at"] or "9"))
    return rows


@r.get("/documents/{doc_id}")
def get_document(doc_id: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    return full(db, u, svc.get_doc(db, u, doc_id))


class TextIn(BaseModel):
    text: str
    title: Optional[str] = None


@r.put("/documents/{doc_id}")
def put_document(doc_id: int, b: TextIn, u: User = Depends(require("Creator")), db: Session = Depends(get_db)):
    d = svc.get_doc(db, u, doc_id)
    svc.set_text(db, u, d, sanitise(b.text))
    if b.title:
        d.title = b.title[:200]
    db.commit()
    return full(db, u, d)


class ToggleIn(BaseModel):
    local_only: bool


@r.put("/documents/{doc_id}/local-only")
def set_local_only(doc_id: int, b: ToggleIn, u: User = Depends(require("Creator")), db: Session = Depends(get_db)):
    d = svc.get_doc(db, u, doc_id)
    svc._need_edit(u, d)
    d.local_only = b.local_only
    svc.audit.log(db, d.tenant_id, u.name, u.role, "Local-only mode " + ("on" if b.local_only else "off"), "", d.id)
    db.commit()
    return full(db, u, d)


@r.post("/documents/{doc_id}/review")
def review(doc_id: int, u: User = Depends(rate_limit), db: Session = Depends(get_db)):
    d = svc.get_doc(db, u, doc_id)
    if u.role != "Creator":
        raise HTTPException(403, "Only the Creator runs a review.")
    svc._need_edit(u, d)
    if d.source_type != "image" and not d.text.strip():
        raise HTTPException(400, "Add some text first.")
    run_review(db, d, u)
    db.commit()
    return full(db, u, d)


class DecideIn(BaseModel):
    action: str
    text: str = ""
    reason: str = ""


@r.post("/documents/{doc_id}/findings/{fid}")
def decide(doc_id: int, fid: int, b: DecideIn, u: User = Depends(require("Creator")), db: Session = Depends(get_db)):
    d = svc.get_doc(db, u, doc_id)
    svc.decide(db, u, d, fid, b.action, b.text, b.reason)
    db.commit()
    return full(db, u, d)


class NoteIn(BaseModel):
    note: str = ""


@r.post("/documents/{doc_id}/{action}")
def workflow(doc_id: int, action: str, b: NoteIn = NoteIn(), u: User = Depends(current_user), db: Session = Depends(get_db)):
    d = svc.get_doc(db, u, doc_id)
    fn = {"submit": lambda: svc.submit(db, u, d), "reviewer-clear": lambda: svc.reviewer_clear(db, u, d, b.note),
          "request-changes": lambda: svc.request_changes(db, u, d, b.note), "approve": lambda: svc.approve(db, u, d, b.note),
          "publish": lambda: svc.publish(db, u, d), "new-revision": lambda: svc.new_revision(db, u, d),
          "comment": lambda: svc.comment(db, u, d, b.note)}.get(action)
    if not fn:
        raise HTTPException(404, "Unknown action.")
    fn()
    db.commit()
    return full(db, u, d)


@r.get("/documents/{doc_id}/diff")
def diff(doc_id: int, a: int, b: Optional[int] = None, u: User = Depends(current_user), db: Session = Depends(get_db)):
    d = svc.get_doc(db, u, doc_id)
    return {"a": a, "b": b if b is not None else "working", "ops": svc.diff(db, d, a, b)}


@r.get("/documents/{doc_id}/audit")
def doc_audit(doc_id: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    d = svc.get_doc(db, u, doc_id)
    return [audit_out(e) for e in db.execute(select(AuditEvent).where(AuditEvent.doc_id == d.id).order_by(AuditEvent.seq.desc())).scalars()]


# ---------- audit ----------
def audit_out(e: AuditEvent) -> dict:
    return {"seq": e.seq, "at": e.at.isoformat(sep=" "), "user": e.user_name, "role": e.role, "action": e.action, "detail": e.detail,
            "doc_id": e.doc_id, "hash": e.hash[:16]}


AUDIT_ROLES = ("Brand Manager", "Brand Admin")


@r.get("/audit")
def audit_list(limit: int = Query(200, le=2000), u: User = Depends(require(*AUDIT_ROLES)), db: Session = Depends(get_db)):
    rows = db.execute(select(AuditEvent).where(AuditEvent.tenant_id == u.tenant_id).order_by(AuditEvent.seq.desc()).limit(limit)).scalars()
    return [audit_out(e) for e in rows]


@r.get("/audit/verify")
def audit_verify(u: User = Depends(require(*AUDIT_ROLES)), db: Session = Depends(get_db)):
    return audit.verify_chain(db, u.tenant_id)


@r.get("/audit/report")
def audit_report(format: str = "txt", u: User = Depends(require(*AUDIT_ROLES)), db: Session = Depends(get_db)):
    rows = db.execute(select(AuditEvent).where(AuditEvent.tenant_id == u.tenant_id).order_by(AuditEvent.seq)).scalars().all()
    chain = audit.verify_chain(db, u.tenant_id)
    if format == "json":
        return {"generated": str(date.today()), "chain": chain, "events": [audit_out(e) for e in rows]}
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["seq", "at", "user", "role", "action", "detail", "doc_id", "hash"])
        for e in rows:
            x = audit_out(e)
            w.writerow([x[k] for k in ("seq", "at", "user", "role", "action", "detail", "doc_id", "hash")])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit.csv"})
    ai = bool(get_provider())
    lines = ["BrandSentinel audit report", f"Generated: {date.today()}", f"Events: {len(rows)}",
             f"Hash chain: {'intact' if chain['ok'] else 'BROKEN at event ' + str(chain['broken_at'])}",
             "AI-use disclosure: " + ("an external model may assist tone and claim checks on non-confidential drafts; see the AI-use log."
                                       if ai else "no LLM or external service is configured; every finding is a Rule or Heuristic."), ""]
    lines += [f"{e.seq} | {e.at} | {e.user_name} ({e.role}) | {e.action} | {e.detail}" for e in rows]
    return PlainTextResponse("\n".join(lines), headers={"Content-Disposition": "attachment; filename=audit-report.txt"})


@r.get("/ai-log")
def ai_log(format: str = "json", u: User = Depends(require(*AUDIT_ROLES)), db: Session = Depends(get_db)):
    rows = db.execute(select(AIUsage).where(AIUsage.tenant_id == u.tenant_id).order_by(AIUsage.id.desc()).limit(2000)).scalars().all()
    out = [{"at": x.at.isoformat(sep=" "), "doc_id": x.doc_id, "purpose": x.purpose, "mode": x.mode, "model": x.model,
            "input_chars": x.input_chars, "returned": x.returned, "kept": x.kept, "latency_ms": x.latency_ms, "detail": x.detail} for x in rows]
    if format == "csv":
        buf = io.StringIO()
        if out:
            w = csv.DictWriter(buf, fieldnames=list(out[0]))
            w.writeheader()
            w.writerows(out)
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=ai-use-log.csv"})
    return out


# ---------- brand kit ----------
def rec_out(k: KitRecord, admin: bool) -> dict:
    hide = k.kind == "sensitive" and not admin
    data = {"text": render_record(Rec(k.rid, k.kind, k.version, k.data, k.valid_to))} if hide else k.data
    return {"rid": k.rid, "kind": k.kind, "version": k.version, "active": k.active, "data": data, "valid_to": k.valid_to.isoformat() if k.valid_to else None,
            "text": "Sensitive-term list (visible to Brand Admins only)." if hide else render_record(Rec(k.rid, k.kind, k.version, k.data, k.valid_to)),
            "created_by": k.created_by, "created_at": k.created_at.isoformat(sep=" "), "note": k.note}


@r.get("/kit")
def kit_list(u: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(KitRecord).where(KitRecord.tenant_id == u.tenant_id, KitRecord.active.is_(True)).order_by(KitRecord.kind, KitRecord.rid)).scalars()
    return {"records": [rec_out(k, u.role == "Brand Admin") for k in rows], "system": [{"rid": k, "text": v} for k, v in SYSTEM_SOURCES.items()]}


class RecIn(BaseModel):
    kind: str
    data: dict
    rid: Optional[str] = None
    valid_to: Optional[str] = None
    note: str = ""


def _reindex(db, u):
    index_kit(db, u.tenant_id, load_kit(db, u.tenant_id))


@r.post("/kit/records")
def kit_save(b: RecIn, u: User = Depends(require("Brand Admin")), db: Session = Depends(get_db)):
    try:
        rec = save_record(db, u.tenant_id, b.kind, b.data, b.rid, parse_date(b.valid_to), u.name, b.note)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e))
    audit.log(db, u.tenant_id, u.name, u.role, "Kit record saved", f"{rec.rid} v{rec.version} ({rec.kind})")
    db.commit()
    _reindex(db, u)
    return rec_out(rec, True)


@r.delete("/kit/records/{rid}")
def kit_retire(rid: str, u: User = Depends(require("Brand Admin")), db: Session = Depends(get_db)):
    k = db.execute(select(KitRecord).where(KitRecord.tenant_id == u.tenant_id, KitRecord.rid == rid, KitRecord.active.is_(True))).scalars().first()
    if not k:
        raise HTTPException(404, "Record not found.")
    k.active = False
    audit.log(db, u.tenant_id, u.name, u.role, "Kit record retired", f"{rid} v{k.version}")
    db.commit()
    _reindex(db, u)
    return {"ok": True}


@r.get("/kit/records/{rid}/history")
def kit_history(rid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(KitRecord).where(KitRecord.tenant_id == u.tenant_id, KitRecord.rid == rid).order_by(KitRecord.version.desc())).scalars().all()
    return [rec_out(k, u.role == "Brand Admin") for k in rows]


class ImportIn(BaseModel):
    filename: str = "kit.txt"
    text: str
    commit: bool = False


def _do_import(db, u, filename: str, text: str, commit: bool):
    try:
        parsed = parse_any(filename, text)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"Could not read this brand kit: {e}")
    recs = parsed["records"]
    if commit:
        n = 0
        for x in recs:
            try:
                save_record(db, u.tenant_id, x["kind"], x["data"], x.get("rid"), parse_date(x.get("valid_to")), u.name, f"Imported from {filename}", merge=True)
                n += 1
            except (ValueError, KeyError, TypeError) as e:
                parsed["warnings"].append(f"Skipped {x['kind']}: {e}")
        audit.log(db, u.tenant_id, u.name, u.role, "Brand kit import", f"{n} records from {filename}")
        db.commit()
        _reindex(db, u)
        parsed["committed"] = n
    return parsed


@r.post("/kit/import")
def kit_import(b: ImportIn, u: User = Depends(require("Brand Admin")), db: Session = Depends(get_db)):
    return _do_import(db, u, b.filename, b.text, b.commit)


@r.post("/kit/import-file")
async def kit_import_file(file: UploadFile = File(...), commit: bool = Form(False), u: User = Depends(require("Brand Admin")), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File is too large.")
    name = file.filename or "kit.txt"
    try:
        text = parse_bytes(name, data).text if name.lower().endswith((".docx", ".pdf")) else data.decode("utf-8", errors="replace")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _do_import(db, u, name, text, commit)


@r.post("/kit/reindex")
def kit_reindex(u: User = Depends(require("Brand Admin")), db: Session = Depends(get_db)):
    return {"chunks": index_kit(db, u.tenant_id, load_kit(db, u.tenant_id))}


# ---------- insights, evaluation ----------
@r.get("/insights")
def get_insights(u: User = Depends(require("Brand Manager", "Brand Admin")), db: Session = Depends(get_db)):
    return insights.compute(db, u.tenant_id)


@r.get("/stale")
def stale(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return insights.stale_alerts(db, u.tenant_id)


@r.get("/eval")
def run_eval(u: User = Depends(require("Brand Manager", "Brand Admin")), db: Session = Depends(get_db)):
    return evaluate(load_kit(db, u.tenant_id))


@r.get("/health")
def health():
    return {"ok": True}


@r.post("/admin/demo-activity")
def demo_activity(u: User = Depends(require("Brand Admin")), db: Session = Depends(get_db)):
    """Populate sample reviewed drafts with creator decisions so the insights dashboard has something to show."""
    from .seed import seed_activity
    if not settings.seed_demo:
        raise HTTPException(404, "Demo data is disabled.")
    return {"decisions": seed_activity(db, u)}
