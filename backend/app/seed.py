"""Seed the demo tenant (Lumora Wellness), demo users and, optionally, demo activity for the insights dashboard."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .kit import load_kit, seed_demo_kit
from .models import Tenant, User
from .retrieval import index_kit
from .security import hash_pw

DEMO_USERS = [("Aria Menon", "aria@lumora.demo", "Creator", "Marketing"), ("Dev Rao", "dev@lumora.demo", "Creator", "Social"),
              ("Leela Iyer", "leela@lumora.demo", "Authorised Reviewer", "Legal"), ("Meera Shah", "meera@lumora.demo", "Brand Manager", "Brand"),
              ("Ishaan Kapoor", "admin@lumora.demo", "Brand Admin", "Brand")]


def seed(db: Session) -> None:
    t = settings.default_tenant
    if not db.get(Tenant, t):
        db.add(Tenant(id=t, name="Lumora Wellness"))
        db.flush()
    seed_demo_kit(db, t)
    if settings.seed_demo and not db.execute(select(User.id)).first():
        pw = hash_pw(settings.demo_password)
        for n, e, r, team in DEMO_USERS:
            db.add(User(tenant_id=t, name=n, email=e, role=r, team=team, password_hash=pw))
    db.commit()
    index_kit(db, t, load_kit(db, t))


def seed_activity(db: Session, admin: User) -> int:
    """Create a handful of reviewed drafts with creator decisions so the insights dashboard has data."""
    from . import services as svc
    from .pipeline import current_findings, run_review
    aria = db.execute(select(User).where(User.email == "aria@lumora.demo")).scalars().first()
    dev = db.execute(select(User).where(User.email == "dev@lumora.demo")).scalars().first()
    if not aria or not dev:
        return 0
    drafts = [(aria, "Spring launch post", "Our customers love the best in the industry classes! Members see 40% better sleep."),
              (aria, "Newsletter", "The fastest way to relax. Guaranteed calm. Customers can sign up today."),
              (dev, "Reel caption", "Obviously you want the #1 studio. Cheap classes, world-class teachers!!"),
              (dev, "Partner email", "Over 9,000 users trust the only wellness app, clinically proven.")]
    n = 0
    for u, title, text in drafts:
        d = svc.create_doc(db, u, title, text, u.team, False)
        run_review(db, d, u)
        _, fs = current_findings(db, d)
        for f in list(fs):
            _, cur = current_findings(db, d)
            f2 = next((x for x in cur if x.key == f.key), None)
            if not f2 or f2.decision:
                continue
            if f2.category == "Unsupported claim":
                svc.decide(db, u, d, f2.id, "dispute", reason="We have the study on file; the rule is unclear about marketing copy.")
            elif f2.rep is not None:
                svc.decide(db, u, d, f2.id, "accept")
            else:
                svc.decide(db, u, d, f2.id, "dispute", reason="Intentional here.")
            n += 1
    db.commit()
    return n
