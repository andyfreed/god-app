import sys
import re
from pathlib import Path

from docx import Document

# Heuristic thresholds — tweak once, reuse everywhere
H1_MIN_PT = 16  # ≥ this size *and* bold → Heading 1
H2_MIN_PT = 14  # ≥ this size (any weight) → Heading 2


def classify(paragraph):
    """Return the Word style name this paragraph *should* have, or None."""
    if not paragraph.text.strip():  # blank lines
        return None

    run = paragraph.runs[0] if paragraph.runs else None
    size = run.font.size.pt if run and run.font.size else 0
    bold = bool(run.bold) if run else False

    if size >= H1_MIN_PT and bold:
        return "Heading 1"
    if size >= H2_MIN_PT:
        return "Heading 2"
    return None  # leave unchanged


def apply_heading_styles(src_path: Path, dst_path: Path):
    """Open *src_path*, fix headings, save to *dst_path*."""
    doc = Document(src_path)
    for para in doc.paragraphs:
        style_name = classify(para)
        if style_name:
            para.style = style_name
    doc.save(dst_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_headings.py <input.docx> [output.docx]")
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) >= 3 else src.with_name(src.stem + "_fixed.docx")

    apply_heading_styles(src, dst)
    print(f"Saved {dst}") 