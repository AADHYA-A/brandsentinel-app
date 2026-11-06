"""Grounded retrieval over the approved brand kit.

Embeddings are a deterministic local hashing embedding (no external model, nothing leaves the host).
On PostgreSQL with the pgvector extension the vectors are also stored in a `vector` column and searched
with cosine distance; otherwise a numpy cosine scan is used (fine for kit-sized corpora)."""
from __future__ import annotations
import hashlib
import re
import numpy as np
from sqlalchemy import delete, select, text as sql
from sqlalchemy.orm import Session
from .kit import Kit
from .models import KitChunk

DIM = 256
_tok = re.compile(r"[a-z0-9₹#%]+")


def embed(t: str) -> list[float]:
    t = t.lower()
    words = _tok.findall(t)
    feats = words + [a + "_" + b for a, b in zip(words, words[1:])] + [t[i:i + 3] for i in range(max(0, len(t) - 2)) if " " not in t[i:i + 3]]
    v = np.zeros(DIM, dtype=np.float32)
    for f in feats:
        h = int(hashlib.md5(f.encode()).hexdigest()[:8], 16)
        v[h % DIM] += 1.0 if (h >> 31) & 1 else -1.0
    n = np.linalg.norm(v)
    return (v / n).tolist() if n else v.tolist()


def _pg(db: Session) -> bool:
    return db.bind is not None and db.bind.dialect.name == "postgresql"


def ensure_pgvector(db: Session) -> bool:
    if not _pg(db):
        return False
    try:
        db.execute(sql("CREATE EXTENSION IF NOT EXISTS vector"))
        db.execute(sql(f"ALTER TABLE kit_chunks ADD COLUMN IF NOT EXISTS embedding_vec vector({DIM})"))
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def index_kit(db: Session, tenant_id: str, kit: Kit) -> int:
    """Rebuild the retrieval index. Sensitive-term records are never indexed (they must not reach a model)."""
    db.execute(delete(KitChunk).where(KitChunk.tenant_id == tenant_id))
    pgv = ensure_pgvector(db)
    n = 0
    for r in kit.records:
        if r.kind == "sensitive":
            continue
        e = embed(f"{r.rid} {r.text}")
        c = KitChunk(tenant_id=tenant_id, rid=r.rid, text=r.text, embedding=e)
        db.add(c)
        db.flush()
        if pgv:
            db.execute(sql("UPDATE kit_chunks SET embedding_vec = CAST(:v AS vector) WHERE id = :i"),
                       {"v": "[" + ",".join(f"{x:.6f}" for x in e) + "]", "i": c.id})
        n += 1
    db.commit()
    return n


def search(db: Session, tenant_id: str, query: str, k: int = 6) -> list[tuple[str, str, float]]:
    q = embed(query)
    if _pg(db):
        try:
            rows = db.execute(sql("SELECT rid, text, 1 - (embedding_vec <=> CAST(:q AS vector)) AS s FROM kit_chunks "
                                  "WHERE tenant_id = :t AND embedding_vec IS NOT NULL ORDER BY embedding_vec <=> CAST(:q AS vector) LIMIT :k"),
                              {"q": "[" + ",".join(f"{x:.6f}" for x in q) + "]", "t": tenant_id, "k": k}).all()
            return [(r[0], r[1], float(r[2])) for r in rows]
        except Exception:
            db.rollback()
    chunks = db.execute(select(KitChunk).where(KitChunk.tenant_id == tenant_id)).scalars().all()
    if not chunks:
        return []
    m = np.array([c.embedding for c in chunks], dtype=np.float32)
    s = m @ np.array(q, dtype=np.float32)
    idx = np.argsort(-s)[:k]
    return [(chunks[i].rid, chunks[i].text, float(s[i])) for i in idx]
