"""Labelled evaluation set (60 author-written snippets) and metric computation.

Expected labels are the kit record ids that SHOULD be cited. Empty list = clean text, nothing should fire.
Run: python -m app.evalset"""
from __future__ import annotations
import time
from datetime import date
from typing import Optional
from .kit import Kit
from .pipeline import review_text

G1, G2, G3, G4, F104, F110, F118, F121 = "G-01", "G-02", "G-03", "G-04", "F-104", "F-110", "F-118", "F-121"
CL, VO, CF = "Claims Policy 4.2", "Voice 2.1", "Confidentiality Policy 7.1"
ALT, CON, LNK = "WCAG 2.2 SC 1.1.1", "WCAG 2.2 SC 1.4.3", "WCAG 2.2 SC 2.4.4"

SEED: list[tuple[str, list[str]]] = [
    # Terminology (8)
    ("Our customers get cheap deals.", [G1, G3]), ("Thanks to all our users!", [G2]), ("Sign up today for a calm start.", [G4]),
    ("CUSTOMERS can pause anytime.", [G1, VO]), ("We love our customers and users.", [G1, G2]), ("A cheap way to try yoga.", [G3]),
    ("New customers receive a welcome kit.", [G1]), ("You can sign up in a minute.", [G4]),
    # Factual accuracy (8)
    ("Over 10,000 members trust us.", [F104]), ("More than 9,000 clients practise with Lumora.", [F104]), ("About 12k users joined this year.", [F104, G2]),
    ("Pro plan is ₹1,299 a month.", [F121]), ("The Pro plan costs just ₹1499 each month.", [F121]), ("Pro plan: ₹499 per month.", [F121]),
    ("Nearly 20,000 members have joined.", [F104]), ("Pro plan is only ₹ 1,100 monthly.", [F121]),
    # Outdated (4)
    ("Try our Starter plan today.", [F110]), ("The Spring Sale is on now.", [F118]), ("Our Starter plan is great value.", [F110]), ("Hurry, the Spring Sale ends soon.", [F118]),
    # Unsupported claims (10)
    ("We are the best in the industry.", [CL]), ("Our #1 rated studio.", [CL]), ("Results are guaranteed.", [CL]), ("A clinically proven routine.", [CL]),
    ("Members see 40% better sleep.", [CL]), ("The only app you will ever need.", [CL]), ("Unbeatable prices all week.", [CL]),
    ("World-class teachers lead every class.", [CL]), ("We guarantee you will feel calmer.", [CL]), ("The fastest way to relax: 25% less stress.", [CL]),
    # Tone (8)
    ("Obviously you will love it.", [VO]), ("Yeah right, as if anyone skips a class.", [VO]), ("Join us today!!", [VO]), ("Our AMAZING classes start Monday.", [VO]),
    ("Whatever, just try it.", [VO]), ("Oh please, it is easy.", [VO]), ("Good luck with that diet.", [VO]), ("Duh, of course it works.", [VO]),
    # Confidentiality (4)
    ("Project Aurora launches next quarter.", [CF]), ("See the Zephyr roadmap for details.", [CF]), ("Our Q4 roadmap includes a new app.", [CF]), ("Sneak peek of Project Helios.", [CF]),
    # Accessibility (6)
    ('<img src="a.png">', [ALT]), ('<p>Hello</p><img src="b.jpg" width="40">', [ALT]), ('<a href="/join">click here</a>', [LNK]),
    ("#aaaaaa on #ffffff", [CON]), ("Banner text: #9aa0a6 on #ffffff", [CON]), ('<p style="color:#bbbbbb;background:#ffffff">Hi</p>', [CON]),
    # Compound (4)
    ("Our Customers LOVE Lumora!! Over 10,000 clients trust us.", [G1, VO, F104]),
    ("The best in the industry: Pro plan is ₹1,299 and the Spring Sale is on.", [CL, F121, F118]),
    ("Obviously, Project Aurora is the only plan for customers.", [VO, CF, CL, G1]),
    ('<img src="x.png"> Cheap, guaranteed results!!', [ALT, G3, CL, VO]),
    # Clean / negative (8)
    ("Welcome, members. We have 7,500 members and the Pro plan is ₹999 a month.", []), ("Join us for a calm, friendly start.", []),
    ("Our members enjoy affordable classes, taught with care.", []), ('<img src="a.png" alt="Members stretching in a sunlit studio">', []),
    ("You might enjoy our evening class.", []), ("Pro plan is ₹999 per month, billed monthly.", []),
    ('<a href="/join">Join Lumora today</a>', []), ('<p style="color:#14213d;background:#ffffff">Hello</p>', []),
]
assert len(SEED) == 60, len(SEED)


def evaluate(kit: Kit, today: Optional[date] = None) -> dict:
    t0 = time.perf_counter()
    exp = hit = flagged = valid = allc = cite_ok = hall_raw = hall_kept = 0
    misses, extras = [], []
    for text, expected in SEED:
        kept, dropped, raw_n, _ = review_text(text, kit, today)
        got = {c.src for c in kept}
        exp += len(expected)
        for x in expected:
            if x in got:
                hit += 1
            else:
                misses.append({"text": text, "missing": x})
        for g in got:
            flagged += 1
            if g in expected:
                valid += 1
            else:
                extras.append({"text": text, "unexpected": g})
        for c in kept:
            allc += 1
            quoted = text[c.start:c.end] == c.text
            if c.src in kit.ids and quoted:
                cite_ok += 1
            if not quoted:
                hall_kept += 1
        hall_raw += sum(1 for d in dropped if "not present" in d["reason"] or "does not match" in d["reason"])
    ms = (time.perf_counter() - t0) * 1000
    pct = lambda a, b: round(100 * a / b) if b else 100
    return {"snippets": len(SEED), "recall": pct(hit, exp), "precision": pct(valid, flagged), "citation_validity": pct(cite_ok, allc),
            "hallucinated_claims": hall_kept, "hallucinations_blocked_by_verifier": hall_raw,
            "ms_total": round(ms), "ms_per_snippet": round(ms / len(SEED), 1), "manual_baseline_days": 2.3,
            "misses": misses[:20], "unexpected": extras[:20],
            "scope": "Deterministic rules and heuristics only. AI-assisted checks are not part of this score."}


if __name__ == "__main__":
    import json
    from .kit import DEMO_KIT, Kit, Rec, parse_date
    k = Kit([Rec(r, kd, 1, d, parse_date(v)) for r, kd, d, v in DEMO_KIT])
    print(json.dumps(evaluate(k), indent=2, ensure_ascii=False))
