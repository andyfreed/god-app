import json
import sys
from pathlib import Path
import tempfile
from typing import Dict, List

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


def render_overlay(page_width, page_height, boxes: List[Dict[str, str]], meta: Dict[str, str]) -> Path:
    """Return path to temporary PDF containing overlay text for a single page."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    c = canvas.Canvas(tmp.name, pagesize=(page_width, page_height))
    for box in boxes:
        field = box["field"]
        text = str(meta.get(field, f"{{{field}}}"))
        x = float(box["x"])
        y = float(box["y"])
        font = box.get("font", "Helvetica")
        size = int(box.get("size", 12))
        c.setFont(font, size)
        c.drawString(x, y, text)
    c.save()
    return Path(tmp.name)


def apply_overlay(base_pdf: Path, overlay_json: Path, meta: Dict[str, str], out_pdf: Path):
    reader = PdfReader(str(base_pdf))
    writer = PdfWriter()

    with open(overlay_json) as f:
        overlay = json.load(f)
    by_page = {}
    for box in overlay.get("fields", []):
        by_page.setdefault(box["page"], []).append(box)

    for idx, page in enumerate(reader.pages, start=1):
        # page numbers in overlay are 1-indexed
        if idx in by_page:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            overlay_pdf_path = render_overlay(w, h, by_page[idx], meta)
            overlay_reader = PdfReader(str(overlay_pdf_path))
            page.merge_page(overlay_reader.pages[0])
            Path(overlay_pdf_path).unlink(missing_ok=True)
        writer.add_page(page)

    with open(out_pdf, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: apply_overlay.py base.pdf overlay.json meta.json out.pdf")
        sys.exit(1)
    base, overlay, meta_json, dest = map(Path, sys.argv[1:5])
    meta_data = json.loads(meta_json.read_text())
    apply_overlay(base, overlay, meta_data, dest) 