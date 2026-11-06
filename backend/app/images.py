"""Image review: palette adherence, contrast, clearspace and alt text.

Findings quote a measurement (for example a hex colour) rather than draft text. Palette, contrast and
clearspace are pixel measurements, labelled Heuristic; the alt-text check is a deterministic Rule."""
from __future__ import annotations
import io
from typing import Optional
from PIL import Image
from .kit import Kit
from .rules import Cand, SYS_ALT, SYS_CONTRAST, contrast


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(c[:3])


def _dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def review_image(data: bytes, alt: str, kit: Kit, text_colour: Optional[str] = None, bg_colour: Optional[str] = None) -> tuple[list[Cand], dict]:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    small = img.copy()
    small.thumbnail((200, 200))
    q = small.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:18]
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    dom = [(c / total, tuple(pal[i * 3:i * 3 + 3])) for c, i in counts]
    stats = {"width": w, "height": h, "dominant": [{"hex": _hex(c), "share": round(s * 100, 1)} for s, c in dom]}
    out: list[Cand] = []
    vis = kit.of("visual")
    v = vis[0] if vis else None

    if not alt.strip():
        out.append(Cand(-1, -1, "missing alt text", "Accessibility", SYS_ALT, "Rule", "Medium", "low",
                        "The image was submitted without alt text, so screen readers cannot describe it.",
                        tip="Add a short description of what the image shows.", conf=98))
    if v:
        palette = [tuple(int(p[i:i + 2], 16) for i in (1, 3, 5)) for p in v.data.get("palette", [])]
        tol = float(v.data.get("tolerance", 60))
        for share, c in dom:
            if share < 0.08 or not palette:
                continue
            nearest = min(palette, key=lambda p: _dist(p, c))
            if _dist(nearest, c) > tol:
                out.append(Cand(-1, -1, _hex(c), "Brand palette", v.rid, "Heuristic", "Medium", "low",
                                f"{_hex(c)} covers about {share * 100:.0f}% of the image and is {_dist(nearest, c):.0f} away from the nearest approved colour.",
                                tip=f"Nearest approved colour: {_hex(nearest)}.", rep=_hex(nearest), conf=72))
        # Contrast: user-supplied text/background colours, else the two most distant dominant colours.
        fg, bg = text_colour, bg_colour
        method, conf = "Rule", 98
        if not (fg and bg) and len(dom) >= 2:
            bgc = dom[0][1]
            far = max(dom[1:], key=lambda d: _dist(d[1], bgc))[1]
            fg, bg, method, conf = _hex(far), _hex(bgc), "Heuristic", 60
        if fg and bg:
            r = contrast(fg, bg)
            mn = float(v.data.get("min_contrast", 4.5))
            if r < mn:
                out.append(Cand(-1, -1, f"{fg} on {bg}", "Accessibility", SYS_CONTRAST, method, "Medium", "low",
                                f"Contrast ratio is {r:.2f}:1; the minimum is {mn}:1." +
                                ("" if method == "Rule" else " Colours were estimated from the image; supply the real text colour to confirm."),
                                tip="Pick a darker text colour or a lighter background.", conf=conf))
        # Clearspace: margin between the image edge and the content bounding box.
        bgc = dom[0][1]
        px = small.load()
        sw, sh = small.size
        xs, ys = [], []
        for y in range(sh):
            for x in range(sw):
                if _dist(px[x, y], bgc) > 40:
                    xs.append(x)
                    ys.append(y)
        if xs:
            m = min(min(xs), min(ys), sw - 1 - max(xs), sh - 1 - max(ys)) / min(sw, sh) * 100
            need = float(v.data.get("min_clearspace_pct", 5))
            stats["clearspace_pct"] = round(m, 1)
            if m < need:
                out.append(Cand(-1, -1, f"{m:.1f}% margin", "Clearspace", v.rid, "Heuristic", "Low", "low",
                                f"Content comes within {m:.1f}% of the edge; the visual rules ask for at least {need:.0f}% clearspace.",
                                tip="Add padding around the logo or main content.", conf=72))
    return out, stats
