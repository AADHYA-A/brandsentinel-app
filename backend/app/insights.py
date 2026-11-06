"""Governance insights: recurring mistakes, guideline-clarity score, stale-fact alerts, review KPIs."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date
from statistics import median
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from .kit import load_kit
from .models import Decision, Document, Finding

BASELINE_DAYS, BASELINE_ROUNDS = 2.3, 2.9
MIN_DECISIONS, AMBIGUOUS_RATE = 3, 50


def stale_alerts(db: Session, tenant_id: str, today: Optional[date] = None, window: int = 180) -> list[dict]:
    today = today or date.today()
    out = []
    for r in load_kit(db, tenant_id).of("fact"):
        if not r.valid_to:
            continue
        d = (r.valid_to - today).days
        triggers = bool(r.data.get("triggers"))
        state = "expired" if d < 0 else "expiring" if d <= window else "current"
        out.append({"rid": r.rid, "text": r.data.get("text", ""), "valid_to": r.valid_to.isoformat(), "days": d, "state": state,
                    "action": ("Drafts mentioning this are flagged as outdated." if state == "expired" and triggers else
                               "Ask the Brand Admin to re-confirm or retire this fact." if state != "current" else "")})
    return sorted(out, key=lambda x: x["days"])


def compute(db: Session, tenant_id: str, today: Optional[date] = None) -> dict:
    ds = db.execute(select(Decision).where(Decision.tenant_id == tenant_id)).scalars().all()
    per: dict[str, dict] = defaultdict(lambda: {"accepted": 0, "disputed": 0, "category": ""})
    team_rule: Counter = Counter()
    for d in ds:
        p = per[d.src]
        p["category"] = d.category
        p["disputed" if d.kind == "disputed" else "accepted"] += 1
        team_rule[(d.team or "Unassigned", d.src, d.category)] += 1
    clarity = []
    for src, p in per.items():
        n = p["accepted"] + p["disputed"]
        rate = round(100 * p["disputed"] / n)
        clarity.append({"src": src, "category": p["category"], "accepted": p["accepted"], "disputed": p["disputed"],
                        "dispute_rate": rate, "clarity_score": 100 - rate,
                        "flag": n >= MIN_DECISIONS and rate >= AMBIGUOUS_RATE,
                        "hint": "Guideline may be unclear. Ask the admin to review the wording or add an evidence record."
                        if n >= MIN_DECISIONS and rate >= AMBIGUOUS_RATE else ""})
    clarity.sort(key=lambda x: (-x["flag"], -x["dispute_rate"]))
    recurring = [{"team": t, "src": s, "category": c, "count": n} for (t, s, c), n in team_rule.most_common(15)]
    # Review KPIs measured from real usage in this tenant (not the survey baseline)
    docs = db.execute(select(Document).where(Document.tenant_id == tenant_id, Document.approved_at.is_not(None))).scalars().all()
    days = [(d.approved_at - d.submitted_at).total_seconds() / 86400 for d in docs if d.submitted_at and d.approved_at]
    rounds = [d.version for d in docs if d.version]
    med = median(days) if days else None
    return {
        "clarity": clarity, "recurring": recurring, "stale": stale_alerts(db, tenant_id, today),
        "decisions": len(ds),
        "kpis": {"approved_documents": len(docs), "median_days_to_approve": round(med, 3) if med is not None else None,
                 "avg_rounds": round(sum(rounds) / len(rounds), 2) if rounds else None,
                 "baseline_days": BASELINE_DAYS, "baseline_rounds": BASELINE_ROUNDS,
                 "review_time_reduction_pct": round(100 * (1 - med / BASELINE_DAYS)) if med is not None else None,
                 "note": "Measured on usage in this workspace. The 40% target must be confirmed in user tests with real reviewers."},
    }
