"""Content intake: text, HTML, DOCX, PDF (with OCR fallback) and images -> normalised text + block map."""
from __future__ import annotations
import io
import re
from dataclasses import dataclass, field

TEXT_EXT = {".txt", ".md", ".markdown", ".html", ".htm"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass
class Parsed:
    text: str
    source_type: str
    blocks: list[dict] = field(default_factory=list)   # {i, start, end, kind, page}
    notes: list[str] = field(default_factory=list)


def sanitise(t: str) -> str:
    """Strip NULs and control characters; content is only ever handled as data."""
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", t)


def _blocks(paras: list[tuple[str, str, int]]) -> Parsed:
    text, blocks, pos = "", [], 0
    for i, (kind, p, page) in enumerate(paras):
        if i:
            text += "\n\n"
            pos += 2
        blocks.append({"i": i, "start": pos, "end": pos + len(p), "kind": kind, "page": page})
        text += p
        pos += len(p)
    return Parsed(text, "text", blocks)


def parse_bytes(filename: str, data: bytes) -> Parsed:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext in TEXT_EXT:
        t = sanitise(data.decode("utf-8", errors="replace"))
        p = Parsed(t, "html" if ext in (".html", ".htm") or re.search(r"<\w+[^>]*>", t) else "text")
        pos = 0
        for i, para in enumerate(re.split(r"\n\s*\n", t)):
            s = t.find(para, pos)
            if para.strip():
                p.blocks.append({"i": len(p.blocks), "start": s, "end": s + len(para), "kind": "paragraph", "page": 1})
            pos = s + len(para)
        return p
    if ext == ".docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        paras = [("heading" if (q.style.name or "").lower().startswith("heading") else "paragraph", sanitise(q.text), 1)
                 for q in d.paragraphs if q.text.strip()]
        for t in d.tables:
            for row in t.rows:
                paras.append(("table", sanitise(" | ".join(c.text.strip() for c in row.cells)), 1))
        p = _blocks(paras)
        p.source_type = "docx"
        return p
    if ext == ".pdf":
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        paras, ocr_used = [], False
        for pn, page in enumerate(rd.pages, 1):
            t = (page.extract_text() or "").strip()
            if len(t) < 20:
                t2 = _ocr_page(data, pn - 1)
                if t2:
                    t, ocr_used = t2, True
            for para in re.split(r"\n\s*\n", sanitise(t)):
                if para.strip():
                    paras.append(("paragraph", re.sub(r"\s*\n\s*", " ", para.strip()), pn))
        p = _blocks(paras)
        p.source_type = "pdf"
        if ocr_used:
            p.notes.append("Some pages were scanned images; text was recovered with OCR and may contain errors.")
        if not paras:
            p.notes.append("No text could be extracted (is OCR installed?).")
        return p
    raise ValueError(f"Unsupported file type '{ext or filename}'. Use .txt, .md, .html, .docx, .pdf or an image.")


def _ocr_page(data: bytes, index: int) -> str:
    try:
        import pypdfium2 as pdfium
        import pytesseract
        img = pdfium.PdfDocument(data)[index].render(scale=2).to_pil()
        return pytesseract.image_to_string(img).strip()
    except Exception:
        return ""


def block_of(blocks: list[dict], start: int):
    for b in blocks:
        if b["start"] <= start <= b["end"]:
            return b
    return None
