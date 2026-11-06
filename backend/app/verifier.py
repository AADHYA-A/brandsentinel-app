"""Control point 1: No valid source = No finding. Rejects ungrounded or hallucinated candidates."""
from __future__ import annotations
from .kit import Kit
from .parser import block_of
from .rules import Cand

CAT_KINDS = {"Tone and voice": {"voice"}, "Unsupported claim": {"claims", "evidence"}, "Terminology": {"glossary"},
             "Factual accuracy": {"fact"}, "Outdated information": {"fact"}, "Confidentiality": {"sensitive"},
             "Accessibility": set(), "Brand palette": {"visual"}, "Clearspace": {"visual"}}
MIN_AI_CONF = 55


def verify(cands: list[Cand], text: str, kit: Kit, is_image: bool = False, blocks=None):
    kept, dropped = [], []

    def drop(c, why):
        dropped.append({"src": c.src, "text": c.text[:80], "method": c.method, "reason": why})

    for c in cands:
        if c.src not in kit.ids:
            drop(c, "cited source does not exist in the approved kit")
            continue
        rec = kit.get(c.src)
        need = CAT_KINDS.get(c.cat)
        if need and rec and rec.kind not in need:
            drop(c, f"source {c.src} is a {rec.kind} record and cannot support a {c.cat} finding")
            continue
        if not is_image:
            if c.start < 0:  # AI quote: must exist verbatim in the draft; locate it
                i = text.find(c.text)
                if i < 0 or not c.text.strip():
                    drop(c, "quoted text is not present in the draft")
                    continue
                c.start, c.end = i, i + len(c.text)
            elif text[c.start:c.end] != c.text:
                drop(c, "quote does not match the draft at its position")
                continue
        if c.method == "AI":
            if (c.conf or 0) < MIN_AI_CONF:
                drop(c, f"AI confidence {c.conf}% is below the {MIN_AI_CONF}% threshold")
                continue
            if c.cat == "Unsupported claim":
                c.sev = "Cannot verify"
                c.risk = "high"
                c.conf = None
            elif c.cat in ("Factual accuracy", "Outdated information"):
                c.sev, c.risk = "High", "high"
        if blocks and c.start >= 0:
            b = block_of(blocks, c.start)
            c.block = b["i"] if b else None
        kept.append(c)
    # An AI finding that overlaps a rule finding in the same category is a duplicate.
    rules = [c for c in kept if c.method != "AI"]
    final = [c for c in kept if c.method != "AI" or not any(r.cat == c.cat and r.start < c.end and c.start < r.end for r in rules)]
    for c in kept:
        if c not in final:
            drop(c, "duplicate of a rule finding")
    final.sort(key=lambda c: (c.start, -c.end))
    return final, dropped
