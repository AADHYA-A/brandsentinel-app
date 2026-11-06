"""Review pipeline: rules -> (AI RAG) -> verifier -> persisted findings with carried-over decisions."""
from __future__ import annotations
import hashlib
import time
from datetime import date
from typing import Optional
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from . import ai as ai_mod
from .images import review_image
from .kit import Kit, load_kit
from .models import AIUsage, Decision, Document, Finding, ReviewRun, User
from .rules import Cand, run_rules
from .verifier import verify
from . import audit, storage


def sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def review_text(text: str, kit: Kit, today: Optional[date] = None, blocks=None, db=None, tenant_id="", local_only=True):
    """Pure review of a string. Returns (kept, dropped, raw_count, ai_result)."""
    raw = run_rules(text, kit, today)
    has_conf = any(c.cat == "Confidentiality" for c in raw)
    res = ai_mod.ai_review(db, tenant_id, text, kit, local_only, has_conf) if db is not None else ai_mod.AIResult([], "not used", "skipped: local-only")
    allc = raw + res.cands
    kept, dropped = verify(allc, text, kit, blocks=blocks)
    return kept, dropped, len(allc), res


def make_keys(items: list[Cand]) -> list[str]:
    n: dict[str, int] = {}
    keys = []
    for c in items:
        k = f"{c.src}|{c.text.lower()}"
        n[k] = n.get(k, 0) + 1
        keys.append(f"{k}#{n[k]}")
    return keys


def run_review(db: Session, doc: Document, user: User, today: Optional[date] = None) -> ReviewRun:
    t0 = time.perf_counter()
    kit = load_kit(db, doc.tenant_id)
    ai_res = ai_mod.AIResult([], "not used", "n/a")
    if doc.source_type == "image":
        data = storage.read(doc.image_path)
        o = doc.meta.get("image_opts", {})
        raw, stats = review_image(data, doc.alt_text, kit, o.get("text_colour"), o.get("bg_colour"))
        doc.meta = {**doc.meta, "image_stats": stats}
        kept, dropped = verify(raw, "", kit, is_image=True)
        raw_n = len(raw)
    else:
        kept, dropped, raw_n, ai_res = review_text(doc.text, kit, today, doc.meta.get("blocks"), db, doc.tenant_id, doc.local_only)
    ms = int((time.perf_counter() - t0) * 1000)
    run = ReviewRun(doc_id=doc.id, text_hash=sha(doc.text + "|" + doc.alt_text), raw_count=raw_n, kept_count=len(kept),
                    dropped=dropped, ms=ms, ai_status=ai_res.status, run_by=user.name)
    db.add(run)
    db.flush()
    prior = {d.finding_key: d for d in db.execute(select(Decision).where(Decision.doc_id == doc.id, Decision.kind == "disputed")).scalars()}
    for c, k in zip(kept, make_keys(kept)):
        d = prior.get(k)
        db.add(Finding(run_id=run.id, doc_id=doc.id, key=k, category=c.cat, severity=c.sev, risk=c.risk, method=c.method, src=c.src,
                       src_text=kit.clause(c.src), text=c.text, start=c.start, end=c.end, why=c.why, tip=c.tip, rep=c.rep,
                       confidence=c.conf, block=c.block, decision="disputed" if d else None, reason=d.reason if d else None))
    db.add(AIUsage(tenant_id=doc.tenant_id, doc_id=doc.id, purpose="tone+claims review", mode=ai_res.mode, model=ai_res.model,
                   input_chars=ai_res.chars, returned=ai_res.returned, kept=sum(1 for c in kept if c.method == "AI"),
                   latency_ms=ai_res.ms, detail=ai_res.status[:300]))
    audit.log(db, doc.tenant_id, user.name, user.role, "Review run",
              f"{len(kept)} findings kept of {raw_n} candidates; AI: {ai_res.status}", doc.id)
    return run


def latest_run(db: Session, doc_id: int) -> Optional[ReviewRun]:
    return db.execute(select(ReviewRun).where(ReviewRun.doc_id == doc_id).order_by(ReviewRun.id.desc()).limit(1)).scalars().first()


def current_findings(db: Session, doc: Document) -> tuple[Optional[ReviewRun], list[Finding]]:
    run = latest_run(db, doc.id)
    if not run:
        return None, []
    fs = db.execute(select(Finding).where(Finding.run_id == run.id).order_by(Finding.start, Finding.id)).scalars().all()
    return run, list(fs)


def review_is_fresh(doc: Document, run: Optional[ReviewRun]) -> bool:
    return bool(run) and run.text_hash == sha(doc.text + "|" + doc.alt_text)
