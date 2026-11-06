"""Authentication (local JWT for dev, OAuth2/OIDC bearer tokens in production), RBAC and rate limiting."""
from __future__ import annotations
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import ROLES, User

bearer = HTTPBearer(auto_error=False)


def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt(rounds=10)).decode()


def check_pw(p: str, h: str) -> bool:
    try:
        return bool(h) and bcrypt.checkpw(p.encode(), h.encode())
    except ValueError:
        return False


def make_token(u: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes)
    return jwt.encode({"sub": str(u.id), "role": u.role, "tenant": u.tenant_id, "exp": exp}, settings.secret_key, algorithm="HS256")


_jwks = None


def _oidc_claims(token: str) -> dict:
    global _jwks
    from jwt import PyJWKClient
    if _jwks is None:
        _jwks = PyJWKClient(settings.oidc_issuer.rstrip("/") + "/.well-known/jwks.json")
    key = _jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=settings.oidc_audience or None, issuer=settings.oidc_issuer)


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Sign in required.")
    try:
        if settings.oidc_issuer:
            c = _oidc_claims(creds.credentials)
            email = c.get("email") or c.get("sub")
            u = db.execute(select(User).where(User.email == email)).scalars().first()
            if not u:   # least privilege: unknown OIDC users start as Creators of the claimed tenant
                role = c.get(settings.oidc_role_claim, "Creator")
                u = User(tenant_id=c.get(settings.oidc_tenant_claim, settings.default_tenant), name=c.get("name", email), email=email,
                         role=role if role in ROLES else "Creator", team=c.get("team", ""))
                db.add(u)
                db.commit()
            return u
        c = jwt.decode(creds.credentials, settings.secret_key, algorithms=["HS256"])
        u = db.get(User, int(c["sub"]))
    except Exception:
        raise HTTPException(401, "Invalid or expired token.")
    if not u:
        raise HTTPException(401, "Unknown user.")
    return u


def require(*roles: str):
    def dep(u: User = Depends(current_user)) -> User:
        if u.role not in roles:
            raise HTTPException(403, f"This action needs one of these roles: {', '.join(roles)}.")
        return u
    return dep


_hits: dict[int, deque] = defaultdict(deque)


def rate_limit(u: User = Depends(current_user)) -> User:
    q, t = _hits[u.id], time.monotonic()
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_min:
        raise HTTPException(429, "Too many review requests. Try again in a minute.")
    q.append(t)
    return u
