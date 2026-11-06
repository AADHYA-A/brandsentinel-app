"""Deterministic rule engine and rule-based heuristics. Every candidate cites a kit record id."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from .kit import Kit, Rec

SYS_ALT, SYS_CONTRAST, SYS_LINK = "WCAG 2.2 SC 1.1.1", "WCAG 2.2 SC 1.4.3", "WCAG 2.2 SC 2.4.4"
TAG = re.compile(r"<[^>]+>")


@dataclass
class Cand:
    start: int
    end: int
    text: str
    cat: str
    src: str
    method: str                 # Rule | Heuristic | AI
    sev: str                    # High | Medium | Low | Cannot verify
    risk: str                   # high | low
    why: str
    tip: Optional[str] = None
    rep: Optional[str] = None
    conf: Optional[int] = None
    block: Optional[int] = None
    extra: dict = field(default_factory=dict)


def prose_mask(t: str) -> str:
    """Blank out HTML tags (same length, so offsets stay valid) so word rules ignore markup."""
    return TAG.sub(lambda m: " " * len(m.group()), t)


def _case(match: str, good: str) -> str:
    if len(match) > 1 and match.isupper():
        return good.upper()
    return good[:1].upper() + good[1:] if match[:1].isupper() else good


def _hex(h: str) -> str:
    h = h.lstrip("#").lower()
    return "".join(c * 2 for c in h) if len(h) == 3 else h


def lum(h: str) -> float:
    c = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16) / 255
        c.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    x, y = lum(_hex(a)), lum(_hex(b))
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def fix_colour(fg: str, bg: str, target: float = 4.5) -> str:
    """Smallest step toward black or white that makes fg readable on bg (the minimal-edit suggestion)."""
    fg, bg = _hex(fg), _hex(bg)
    r = [int(fg[i:i + 2], 16) for i in (0, 2, 4)]
    goal = 0 if lum(bg) > 0.18 else 255
    for step in range(0, 101):
        k = step / 100
        c = [round(v + (goal - v) * k) for v in r]
        hx = "".join(f"{x:02x}" for x in c)
        if contrast(hx, bg) >= target:
            return "#" + hx
    return "#000000" if goal == 0 else "#ffffff"


def _phrase_re(p: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(p) + r"(?!\w)", re.I)


def run_rules(text: str, kit: Kit, today: Optional[date] = None) -> list[Cand]:
    today = today or date.today()
    out: list[Cand] = []
    prose = prose_mask(text)

    def add(m, **kw):
        out.append(Cand(start=m.start(), end=m.end(), text=m.group(), **kw))

    # Terminology: deterministic glossary match
    for r in kit.of("glossary"):
        bad, good = r.data.get("bad", ""), r.data.get("good", "")
        if not bad:
            continue
        for m in _phrase_re(bad).finditer(prose):
            add(m, cat="Terminology", src=r.rid, method="Rule", sev="Low", risk="low", conf=98,
                why=f"Glossary {r.rid}: the approved term is “{good}”.", rep=_case(m.group(), good))

    # Factual accuracy: claim extraction against fact records
    for r in kit.of("fact"):
        chk = r.data.get("check")
        if not chk:
            continue
        if chk["type"] == "count":
            nouns = "|".join(re.escape(n) for n in chk.get("nouns", ["members"]))
            rx = re.compile(r"(?:\b(?:over|more than|nearly|about|almost|around)\s+)?(\d[\d,]*(?:\.\d+)?)\s?([kK])?\+?\s+(?:active\s+)?(?:" + nouns + r")\b", re.I)
            for m in rx.finditer(prose):
                v = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
                if abs(v - float(chk["value"])) > 0.5:
                    canon = chk.get("canonical", "members")
                    add(m, cat="Factual accuracy", src=r.rid, method="Rule", sev="High", risk="high", conf=98,
                        why=f"Fact record {r.rid} says: {r.data['text']}.", rep=f"{int(chk['value']):,} {canon}")
        elif chk["type"] == "price":
            cur = r"(?:₹|Rs\.?|INR)" if chk.get("currency", "₹") == "₹" else re.escape(chk["currency"])
            rx = re.compile(re.escape(chk["anchor"]) + r"[^.\n]{0,40}?(" + cur + r")\s?([\d,]+(?:\.\d+)?)", re.I)
            for m in rx.finditer(prose):
                v = float(m.group(2).replace(",", ""))
                if abs(v - float(chk["value"])) > 0.005:
                    seg = m.group(0)
                    rep = seg[: seg.rfind(m.group(2))] + f"{int(chk['value']):,}".replace(",", "") + seg[seg.rfind(m.group(2)) + len(m.group(2)):]
                    add(m, cat="Factual accuracy", src=r.rid, method="Rule", sev="High", risk="high", conf=98,
                        why=f"Fact record {r.rid} says: {r.data['text']}.", rep=rep)

    # Outdated information: validity-date checking
    for r in kit.of("fact"):
        if r.valid_to and r.valid_to < today:
            for t in r.data.get("triggers", []):
                for m in _phrase_re(t).finditer(prose):
                    add(m, cat="Outdated information", src=r.rid, method="Rule", sev="High", risk="high", conf=98,
                        why=f"Fact record {r.rid} expired on {r.valid_to.isoformat()}: “{r.data['text']}”.",
                        tip="Remove the reference or ask the Brand Admin for a current fact record.")

    # Evidence on file suppresses claim findings it covers
    ev_spans: list[tuple[int, int]] = []
    for r in kit.of("evidence"):
        if r.valid_to and r.valid_to < today:
            continue
        for p in r.data.get("phrases", []):
            ev_spans += [(m.start(), m.end()) for m in _phrase_re(p).finditer(prose)]

    def covered(s, e):
        return any(s < ee and es < e for es, ee in ev_spans)

    # Unsupported claims: superlatives, guarantees, statistics
    claims = kit.of("claims")
    cid = claims[0].rid if claims else None
    if cid:
        phrases = sorted({p for c in claims for p in c.data.get("phrases", [])}, key=len, reverse=True)
        taken: list[tuple[int, int]] = []
        for p in phrases:
            for m in _phrase_re(p).finditer(prose):
                if covered(m.start(), m.end()) or any(m.start() < e and s < m.end() for s, e in taken):
                    continue
                taken.append((m.start(), m.end()))
                add(m, cat="Unsupported claim", src=cid, method="Rule", sev="Cannot verify", risk="high",
                    why="No evidence record for this superlative or guarantee exists in the approved sources, so it cannot be verified.",
                    tip="Remove it, or dispute with a pointer to your evidence so a reviewer can check.")
        for m in re.finditer(r"\b\d+(?:\.\d+)?%(?:[^.!?\n<]{0,28})", prose):
            s = m.group().rstrip()
            if covered(m.start(), m.start() + len(s)):
                continue
            out.append(Cand(m.start(), m.start() + len(s), s, "Unsupported claim", cid, "Rule", "Cannot verify", "high",
                            "This statistic has no matching fact or evidence record, so it cannot be verified.",
                            tip="Attach an evidence record or remove the number."))

    # Tone and voice (rule-based heuristics; AI scoring is added in ai.py when enabled)
    voices = kit.of("voice")
    if voices:
        v = voices[0]
        for p in v.data.get("banned", []):
            for m in _phrase_re(p).finditer(prose):
                add(m, cat="Tone and voice", src=v.rid, method="Heuristic", sev="Medium", risk="low", conf=72,
                    why="Sarcastic or dismissive phrasing conflicts with the warm, empathetic voice.",
                    tip="Rephrase warmly, for example “you might enjoy…”.")
        for m in re.finditer(r"!{2,}", prose):
            add(m, cat="Tone and voice", src=v.rid, method="Heuristic", sev="Low", risk="low", conf=72,
                why="Repeated exclamation marks read as shouting.", rep="!")
        allow = {a.upper() for a in v.data.get("allow_caps", [])}
        for m in re.finditer(r"\b[A-Z]{4,}\b", prose):
            if m.group() in allow:
                continue
            add(m, cat="Tone and voice", src=v.rid, method="Heuristic", sev="Low", risk="low", conf=72,
                why="All-caps words read as shouting.", rep=m.group().lower())

    # Confidentiality: sensitive term list and entity filter
    for r in kit.of("sensitive"):
        seen = set()
        for t in r.data.get("terms", []):
            for m in _phrase_re(t).finditer(prose):
                seen.add((m.start(), m.end()))
                add(m, cat="Confidentiality", src=r.rid, method="Rule", sev="High", risk="high", conf=98,
                    why=f"“{m.group()}” is on the sensitive-term list and must not appear in public drafts.", rep="")
        for pat in r.data.get("entity_patterns", []):
            for m in re.finditer(pat, prose):
                if (m.start(), m.end()) in seen:
                    continue
                add(m, cat="Confidentiality", src=r.rid, method="Heuristic", sev="High", risk="high", conf=72,
                    why=f"“{m.group()}” looks like an internal codename (entity filter). Confirm it is cleared for public use.", rep="")

    # Accessibility: deterministic WCAG 2.2 checks (run on the raw text, markup included)
    for m in re.finditer(r"<img\b(?![^>]*\balt\s*=)[^>]*>", text, re.I):
        add(m, cat="Accessibility", src=SYS_ALT, method="Rule", sev="Medium", risk="low", conf=98,
            why="Image has no alt attribute, so screen readers cannot describe it.", tip="Add alt text that describes the image.")
    vague = r"click here|here|read more|learn more|more|link|this link"
    for m in re.finditer(r"<a\b[^>]*>\s*(" + vague + r")\s*</a>", text, re.I):
        add(m, cat="Accessibility", src=SYS_LINK, method="Rule", sev="Low", risk="low", conf=98,
            why="Link text should describe its destination.", tip="Use descriptive text such as “Join Lumora”.")
    for m in re.finditer(r"\bclick here\b", prose, re.I):
        if not any(c.cat == "Accessibility" and c.start <= m.start() < c.end for c in out):
            add(m, cat="Accessibility", src=SYS_LINK, method="Rule", sev="Low", risk="low", conf=98,
                why="Link text should describe its destination.", tip="Use descriptive text such as “Join Lumora”.")
    hx = r"#(?:[0-9a-f]{6}|[0-9a-f]{3})\b"
    for m in re.finditer(r"(" + hx + r")\s*(?:on|over)\s*(" + hx + r")", text, re.I):
        _contrast(out, m, m.group(1), m.group(2), m.group(0))
    for m in re.finditer(r"<[^>]*\bstyle\s*=\s*([\"'])(.*?)\1[^>]*>", text, re.I | re.S):
        st = m.group()
        fg = re.search(r"(?<![-\w])color\s*:\s*(" + hx + ")", st, re.I)
        bg = re.search(r"background(?:-color)?\s*:\s*(" + hx + ")", st, re.I)
        if fg and bg:
            _contrast(out, m, fg.group(1), bg.group(1), fg.group(0), fix_in=m.group())
    return out


def _contrast(out, m, fg, bg, quote, fix_in=None):
    r = contrast(fg, bg)
    if r >= 4.5:
        return
    new = fix_colour(fg, bg)
    rep = (fix_in.replace(fg, new, 1) if fix_in else quote.replace(fg, new, 1))
    start, end, q = (m.start(), m.end(), m.group(0))
    out.append(Cand(start, end, q, "Accessibility", SYS_CONTRAST, "Rule", "Medium", "low",
                    f"Contrast ratio is {r:.2f}:1; the minimum is 4.5:1.", rep=rep, conf=98,
                    tip=f"Use {new} for the text colour ({contrast(new, bg):.1f}:1 on the background)."))
