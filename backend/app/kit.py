"""Brand kit: versioned records, in-memory snapshot for the engines, and the importer."""
from __future__ import annotations
import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import KitRecord

# Sources that are built into the product (not editable brand content).
SYSTEM_SOURCES = {
    "WCAG 2.2 SC 1.1.1": "Non-text content needs a text alternative.",
    "WCAG 2.2 SC 1.4.3": "Text needs a contrast ratio of at least 4.5:1 (3:1 for large text).",
    "WCAG 2.2 SC 2.4.4": "The purpose of a link can be determined from the link text.",
}

ID_PREFIX = {"glossary": "G-", "fact": "F-", "evidence": "E-"}
SPECIAL_IDS = {"voice": "Voice 2.1", "claims": "Claims Policy 4.2",
               "sensitive": "Confidentiality Policy 7.1", "visual": "Visual 1.1"}


@dataclass
class Rec:
    rid: str
    kind: str
    version: int
    data: dict
    valid_to: Optional[date]

    @property
    def text(self) -> str:
        return render_record(self)


@dataclass
class Kit:
    records: list[Rec] = field(default_factory=list)

    def of(self, kind: str) -> list[Rec]:
        return [r for r in self.records if r.kind == kind]

    def get(self, rid: str) -> Optional[Rec]:
        return next((r for r in self.records if r.rid == rid), None)

    @property
    def ids(self) -> set[str]:
        return {r.rid for r in self.records} | set(SYSTEM_SOURCES)

    def clause(self, rid: str) -> str:
        r = self.get(rid)
        if r:
            return r.text if r.kind != "sensitive" else "Sensitive-term list (visible to Brand Admins only)."
        return SYSTEM_SOURCES.get(rid, "")


def render_record(r: Rec) -> str:
    d = r.data
    if r.kind == "glossary":
        return f"Avoid “{d.get('bad','')}”; use “{d.get('good','')}”." + (f" {d['note']}" if d.get("note") else "")
    if r.kind == "fact":
        s = d.get("text", "")
        return s + (f" (valid to {r.valid_to.isoformat()})" if r.valid_to else "")
    if r.kind == "voice":
        return d.get("text", "")
    if r.kind == "claims":
        return d.get("text", "")
    if r.kind == "evidence":
        return f"Evidence on file for “{d.get('claim','')}”: {d.get('source','')}"
    if r.kind == "sensitive":
        return d.get("text", "Sensitive terms must not appear in public drafts.")
    if r.kind == "visual":
        return d.get("text", "Visual identity rules.")
    return ""


def load_kit(db: Session, tenant_id: str) -> Kit:
    rows = db.execute(select(KitRecord).where(KitRecord.tenant_id == tenant_id, KitRecord.active.is_(True))
                      .order_by(KitRecord.kind, KitRecord.rid)).scalars().all()
    return Kit([Rec(r.rid, r.kind, r.version, r.data or {}, r.valid_to) for r in rows])


def next_id(db: Session, tenant_id: str, kind: str) -> str:
    if kind in SPECIAL_IDS:
        return SPECIAL_IDS[kind]
    pref = ID_PREFIX[kind]
    width = 3 if kind == "fact" else 2
    ids = db.execute(select(KitRecord.rid).where(KitRecord.tenant_id == tenant_id, KitRecord.kind == kind)).scalars().all()
    n = max([int(re.sub(r"\D", "", i) or 0) for i in ids] + [100 if kind == "fact" else 0]) + 1
    return f"{pref}{str(n).zfill(width)}"


def _compile_ok(pat: str) -> bool:
    """Admin-supplied regexes are limited in size and refuse nested quantifiers (ReDoS guard)."""
    if len(pat) > 100 or re.search(r"(\+|\*|\})\)?[+*{]", pat):
        return False
    try:
        re.compile(pat)
    except re.error:
        return False
    return True


def validate_data(kind: str, data: dict) -> dict:
    """Light schema check; raises ValueError with a readable message."""
    d = dict(data)
    if kind == "glossary":
        if not str(d.get("bad", "")).strip() or not str(d.get("good", "")).strip():
            raise ValueError("A glossary term needs both 'bad' and 'good'.")
        d["bad"] = re.sub(r"[^\w \-']", "", str(d["bad"])).strip()
        d["good"] = str(d["good"]).strip()
    elif kind == "fact":
        if not str(d.get("text", "")).strip():
            raise ValueError("A fact record needs text.")
        d["triggers"] = [str(t).strip() for t in d.get("triggers", []) if str(t).strip()]
        chk = d.get("check")
        if chk:
            if chk.get("type") not in ("count", "price"):
                raise ValueError("Fact check type must be 'count' or 'price'.")
            float(chk.get("value"))
    elif kind == "claims":
        d["phrases"] = [str(p).strip() for p in d.get("phrases", []) if str(p).strip()]
        d["text"] = d.get("text") or "Superlatives, guarantees and statistics need an evidence record on file."
    elif kind == "evidence":
        d["phrases"] = [str(p).strip() for p in d.get("phrases", []) if str(p).strip()] or ([d["claim"]] if d.get("claim") else [])
        if not d["phrases"]:
            raise ValueError("Evidence needs the claim text it supports.")
    elif kind == "sensitive":
        d["terms"] = [str(t).strip() for t in d.get("terms", []) if str(t).strip()]
        pats = [str(p) for p in d.get("entity_patterns", [])]
        bad = [p for p in pats if not _compile_ok(p)]
        if bad:
            raise ValueError(f"Unsafe or invalid pattern: {bad[0]}")
        d["entity_patterns"] = pats
    elif kind == "voice":
        d["banned"] = [str(t).strip() for t in d.get("banned", []) if str(t).strip()]
        d["allow_caps"] = [str(t).strip() for t in d.get("allow_caps", []) if str(t).strip()]
    elif kind == "visual":
        pal = [p.lower() for p in d.get("palette", [])]
        if any(not re.fullmatch(r"#[0-9a-f]{6}", p) for p in pal):
            raise ValueError("Palette colours must be 6-digit hex values like #0f766e.")
        d["palette"] = pal
    else:
        raise ValueError(f"Unknown record kind: {kind}")
    return d


MERGE_KEYS = ("terms", "phrases", "banned", "allow_caps", "palette", "entity_patterns")


def save_record(db: Session, tenant_id: str, kind: str, data: dict, rid: Optional[str], valid_to: Optional[date],
                user: str, note: str = "", merge: bool = False) -> KitRecord:
    """Create a record, or a new version of an existing one (old version stays in history).

    Policy-style kinds (voice, claims, sensitive, visual) have one fixed id; saving one again makes a new version.
    With merge=True (used by imports) list fields are added to the existing record instead of replacing it."""
    if not rid and kind in SPECIAL_IDS:
        rid = SPECIAL_IDS[kind]
    if rid and merge:
        cur = db.execute(select(KitRecord).where(KitRecord.tenant_id == tenant_id, KitRecord.rid == rid, KitRecord.active.is_(True))).scalars().first()
        if cur:
            data = dict(data)
            for k in MERGE_KEYS:
                if k in data or k in cur.data:
                    data[k] = list(dict.fromkeys([*cur.data.get(k, []), *data.get(k, [])]))
            data = {**cur.data, **{k: v for k, v in data.items() if v not in (None, "")}}
    data = validate_data(kind, data)
    version = 1
    if rid:
        prev = db.execute(select(KitRecord).where(KitRecord.tenant_id == tenant_id, KitRecord.rid == rid,
                                                  KitRecord.active.is_(True))).scalars().first()
        if prev:
            if prev.kind != kind:
                raise ValueError("Record kind cannot change.")
            prev.active = False
            version = prev.version + 1
    else:
        rid = next_id(db, tenant_id, kind)
    rec = KitRecord(tenant_id=tenant_id, rid=rid, kind=kind, version=version, active=True, data=data,
                    valid_to=valid_to, note=note, created_by=user)
    db.add(rec)
    db.flush()
    return rec


# ---------- Importer: structured records parsed out of a brand kit document ----------

HEADING = re.compile(r"^\s*(?:#{1,4}\s*|\d+[.)]\s+)?(glossary|terminology|terms|facts?|fact records?|voice|tone|claims?|"
                     r"evidence|confidential\w*|sensitive\w*|visual|palette)\b[^\n]*$", re.I)
KIND_OF = {"glossary": "glossary", "terminology": "glossary", "terms": "glossary", "fact": "fact", "facts": "fact",
           "fact record": "fact", "fact records": "fact", "voice": "voice", "tone": "voice", "claim": "claims",
           "claims": "claims", "evidence": "evidence", "visual": "visual", "palette": "visual"}
ARROW = re.compile(r"^(?:avoid\s+)?[\"“']?(?P<bad>[^=\"”>→-][^=→>\"”]*?)[\"”']?\s*(?:=>|->|→|—>|use instead:?|should be|use)\s*[\"“']?(?P<good>[^\"”]+?)[\"”']?\s*$", re.I)
DATE = re.compile(r"(?:valid\s*(?:to|until|through)|expires?|ended?\s*on|until)[:\s]*(\d{4}-\d{2}-\d{2})", re.I)


def parse_kit_text(text: str) -> dict:
    """Parse a sectioned plain-text/markdown brand kit into records.

    Sections are recognised by heading words (Glossary, Facts, Voice, Claims, Evidence, Confidential,
    Palette). Items are bullets or lines. Nothing is committed until an admin confirms the preview."""
    out: list[dict] = []
    warnings: list[str] = []
    kind = None
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*•").strip()
        if not line:
            continue
        h = HEADING.match(raw)
        if h and len(line) < 60 and not ARROW.match(line):
            w = h.group(1).lower()
            kind = "sensitive" if w.startswith(("confiden", "sensitive")) else KIND_OF.get(w)
            continue
        if kind is None:
            continue
        try:
            if kind == "glossary":
                m = ARROW.match(line)
                if not m:
                    warnings.append(f"Skipped (expected 'avoid => use'): {line[:80]}")
                    continue
                out.append({"kind": "glossary", "data": {"bad": m["bad"].strip(), "good": m["good"].strip()}})
            elif kind == "fact":
                vt = DATE.search(line)
                body = re.sub(r"^F-\d+\s*[:.-]\s*", "", DATE.sub("", line).split("|")[0]).strip(" ;,.")
                data: dict[str, Any] = {"text": body, "triggers": []}
                for part in line.split("|")[1:]:
                    k, _, v = part.partition("=")
                    k, v = k.strip().lower(), v.strip()
                    if k == "triggers":
                        data["triggers"] = [t.strip() for t in v.split(",") if t.strip()]
                    elif k == "count":     # count=members:7500
                        n, _, val = v.partition(":")
                        data["check"] = {"type": "count", "nouns": ["members", "customers", "clients", "users"],
                                         "canonical": n.strip() or "members", "value": float(val.replace(",", ""))}
                    elif k == "price":     # price=Pro plan:₹:999
                        a, c, val = (v.split(":") + ["", "", ""])[:3]
                        data["check"] = {"type": "price", "anchor": a.strip(), "currency": c.strip() or "₹",
                                         "value": float(val.replace(",", ""))}
                    elif k in ("valid_to", "valid-to"):
                        vt = re.search(r"\d{4}-\d{2}-\d{2}", v)
                out.append({"kind": "fact", "data": data, "valid_to": vt.group(1) if vt and vt.lastindex else (vt.group(0) if vt else None)})
            elif kind == "voice":
                out.append({"kind": "voice", "data": {"text": line, "banned": [], "allow_caps": []}})
            elif kind == "claims":
                phr = re.findall(r"[\"“]([^\"”]+)[\"”]", line)
                out.append({"kind": "claims", "data": {"text": line, "phrases": phr}})
            elif kind == "evidence":
                m = re.match(r"[\"“]?(.+?)[\"”]?\s*(?:=>|->|→|:)\s*(.+)", line)
                if m:
                    out.append({"kind": "evidence", "data": {"claim": m[1].strip(), "phrases": [m[1].strip()], "source": m[2].strip()},
                                "valid_to": (DATE.search(line).group(1) if DATE.search(line) else None)})
            elif kind == "sensitive":
                out.append({"kind": "sensitive", "data": {"terms": [t.strip() for t in re.split(r"[,;]", line) if t.strip()]}})
            elif kind == "visual":
                cols = re.findall(r"#[0-9a-fA-F]{6}", line)
                if cols:
                    out.append({"kind": "visual", "data": {"palette": [c.lower() for c in cols]}})
        except (ValueError, TypeError) as e:
            warnings.append(f"Skipped ({e}): {line[:80]}")
    return {"records": out, "warnings": warnings}


def parse_kit_json(text: str) -> dict:
    j = json.loads(text)
    out, warnings = [], []
    for g in j.get("glossary", []):
        out.append({"kind": "glossary", "data": {"bad": g.get("bad"), "good": g.get("good")}})
    for f in j.get("facts", []):
        f = dict(f)
        vt = f.pop("valid_to", None)
        out.append({"kind": "fact", "data": f, "valid_to": vt, "rid": f.pop("id", None)})
    for k in ("voice", "claims", "evidence", "sensitive", "visual"):
        v = j.get(k)
        for item in (v if isinstance(v, list) else [v] if isinstance(v, dict) else []):
            out.append({"kind": k, "data": item})
    return {"records": out, "warnings": warnings}


def parse_kit_csv(text: str) -> dict:
    out, warnings = [], []
    for row in csv.DictReader(io.StringIO(text)):
        kind = (row.get("kind") or "glossary").strip().lower()
        if kind == "glossary":
            out.append({"kind": "glossary", "data": {"bad": row.get("bad") or row.get("avoid"), "good": row.get("good") or row.get("use")}})
        else:
            warnings.append(f"CSV import supports glossary rows only; skipped kind '{kind}'.")
    return {"records": out, "warnings": warnings}


def parse_any(filename: str, text: str) -> dict:
    n = filename.lower()
    t = text.lstrip()
    if n.endswith(".json") or t.startswith("{"):
        return parse_kit_json(text)
    if n.endswith(".csv"):
        return parse_kit_csv(text)
    return parse_kit_text(text)


def parse_date(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


# ---------- Demo kit (Lumora Wellness) ----------

DEMO_KIT: list[tuple[str, str, dict, Optional[str]]] = [
    ("G-01", "glossary", {"bad": "customers", "good": "members"}, None),
    ("G-02", "glossary", {"bad": "users", "good": "members"}, None),
    ("G-03", "glossary", {"bad": "cheap", "good": "affordable"}, None),
    ("G-04", "glossary", {"bad": "sign up", "good": "join"}, None),
    ("F-104", "fact", {"text": "Lumora has 7,500 active members", "triggers": [],
                       "check": {"type": "count", "nouns": ["members", "customers", "clients", "users"], "canonical": "members", "value": 7500}}, "2027-03-31"),
    ("F-110", "fact", {"text": "The Starter plan was discontinued on 30 Jun 2026", "triggers": ["Starter plan"]}, "2026-06-30"),
    ("F-118", "fact", {"text": "The Spring Sale ended on 30 Sep 2026", "triggers": ["Spring Sale"]}, "2026-09-30"),
    ("F-121", "fact", {"text": "Pro plan costs ₹999 per month", "triggers": [],
                       "check": {"type": "price", "anchor": "Pro plan", "currency": "₹", "value": 999}}, "2027-03-31"),
    ("Voice 2.1", "voice", {"text": "Warm and empathetic. Never sarcastic, never shouting.",
                            "banned": ["obviously", "yeah right", "as if", "whatever", "duh", "oh please", "good luck with that", "you'd be silly"],
                            "allow_caps": ["HTML", "WCAG", "FAQ", "USA", "UK", "INR"]}, None),
    ("Claims Policy 4.2", "claims", {"text": "Superlatives, guarantees and statistics need an evidence record on file.",
                                     "phrases": ["best in the industry", "best in class", "best in the market", "best in the world",
                                                 "#1", "number one", "guarantee", "guaranteed", "guarantees", "clinically proven",
                                                 "unbeatable", "world-class", "the best", "the fastest", "the only"]}, None),
    ("Confidentiality Policy 7.1", "sensitive", {"text": "Unreleased product names and internal roadmaps must not appear in public drafts.",
                                                 "terms": ["Project Aurora", "Zephyr roadmap", "Q4 roadmap"],
                                                 "entity_patterns": [r"\bProject\s+[A-Z][a-z]{3,}\b"]}, None),
    ("Visual 1.1", "visual", {"text": "Approved palette, 4.5:1 text contrast, 5% clearspace, alt text on every image.",
                              "palette": ["#0f766e", "#14213d", "#ffffff", "#f6f7f9", "#d7f0ec"], "tolerance": 60,
                              "min_contrast": 4.5, "min_clearspace_pct": 5}, None),
]


def seed_demo_kit(db: Session, tenant_id: str) -> None:
    if db.execute(select(KitRecord.id).where(KitRecord.tenant_id == tenant_id)).first():
        return
    for rid, kind, data, vt in DEMO_KIT:
        db.add(KitRecord(tenant_id=tenant_id, rid=rid, kind=kind, version=1, active=True, data=data,
                         valid_to=parse_date(vt), created_by="seed"))
    db.flush()
