import argparse
import subprocess
import sys
import tempfile
import shutil
import importlib.util
from pathlib import Path
from datetime import date

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from apply_overlay import apply_overlay  # local util

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "templates"
COVER_TEMPLATE = TEMPLATE_DIR / "cover.html"

# External commands expected on PATH
PANDOC = "pandoc"          # DOCX → PDF (body)
# Prefer WeasyPrint (pure‑python) for HTML → PDF
WKHTMLTOPDF = "wkhtmltopdf"  # legacy fallback
PDFTK = "pdftk"              # merge PDFs (could swap with qpdf)

# CLI fallback path
WEASYPRINT_CLI = "weasyprint"


class BuildError(RuntimeError):
    pass


def run(cmd, **kwargs):
    """Run *cmd* (list or str). Raise BuildError on non‑zero exit."""
    print("·", " " .join(cmd) if isinstance(cmd, list) else cmd)
    result = subprocess.run(cmd, shell=isinstance(cmd, str), **kwargs)
    if result.returncode != 0:
        raise BuildError(f"Command failed: {cmd}")
    return result


def fix_headings(src_docx: Path) -> Path:
    """Return path to a *_fixed.docx* with cleaned heading styles."""
    fixed = src_docx.with_name(src_docx.stem + "_fixed.docx")
    script = REPO_ROOT / "scripts" / "fix_headings.py"
    run([sys.executable, str(script), str(src_docx), str(fixed)])
    return fixed


def extract_cover_from_source(src_pdf: Path, pages: int, out_pdf: Path):
    """Extract *pages* pages from *src_pdf* → *out_pdf* using pdftk."""
    run([PDFTK, str(src_pdf), "cat", f"1-{pages}", "output", str(out_pdf)])


def render_cover(meta: dict, out_pdf: Path):
    """Render or obtain a cover PDF.

    Strategy:
      • If metadata specifies 'cover_source_pdf', extract first 'cover_pages' pages
        (default 3) from that file in the source directory.
      • Otherwise fall back to HTML template rendering using WeasyPrint / wkhtmltopdf.
    """

    # 1. Try metadata‑specified source PDF
    cover_src = meta.get("cover_source_pdf")
    pages = int(meta.get("cover_pages", 3))
    if cover_src:
        cover_path = (REPO_ROOT / cover_src).expanduser()
        if cover_path.exists():
            extract_cover_from_source(cover_path, pages, out_pdf)
            return
        else:
            print(f"⚠️  cover_source_pdf specified but not found: {cover_path}")

    # 2. Try heuristics: look for any PDF in same directory containing 'final result'
    possible = list(out_pdf.parent.parent / 'source' / Path('dummy').parent)

    # fallback to template rendering below

    # ---------- template rendering path ----------
    # Preference order:
    #   1. WeasyPrint CLI (brew install weasyprint)
    #   2. WeasyPrint Python library (pip install weasyprint && brew deps)
    #   3. wkhtmltopdf binary
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("cover.html")
    html_content = template.render(**meta)

    # Option 1: Homebrew weasyprint CLI (preferred on macOS)
    brew_weasy = Path("/opt/homebrew/bin/weasyprint")
    if brew_weasy.exists():
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name
        run([str(brew_weasy), tmp_path, str(out_pdf)])
        Path(tmp_path).unlink(missing_ok=True)
        return

    # Option 1b: generic weasyprint CLI found in PATH
    if shutil.which(WEASYPRINT_CLI):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name
        run([WEASYPRINT_CLI, tmp_path, str(out_pdf)])
        Path(tmp_path).unlink(missing_ok=True)
        return

    # Option 2: Python library (pip install weasyprint && brew deps)
    if importlib.util.find_spec("weasyprint"):
        try:
            from weasyprint import HTML
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
                tmp.write(html_content)
                tmp_path = tmp.name
            HTML(tmp_path, base_url=str(TEMPLATE_DIR)).write_pdf(str(out_pdf))
            Path(tmp_path).unlink(missing_ok=True)
            return
        except Exception as exc:
            print("⚠️  WeasyPrint Python library failed:", exc)
            # continue to next fallback

    # Option 3: wkhtmltopdf binary
    if shutil.which(WKHTMLTOPDF):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name
        run([WKHTMLTOPDF, tmp_path, str(out_pdf)])
        Path(tmp_path).unlink(missing_ok=True)
        return

    raise BuildError("No renderer available. Install: brew install weasyprint  •or•  pip install weasyprint && brew deps  •or•  brew install wkhtmltopdf (deprecated)")


def body_pdf(fixed_docx: Path, out_pdf: Path):
    """Convert *fixed_docx* to PDF with TOC/bookmarks using Pandoc."""
    cmd = [
        PANDOC,
        str(fixed_docx),
        "--from=docx",
        "--to=pdf",
        "--pdf-engine=/opt/homebrew/bin/weasyprint",
        "--table-of-contents",
        "--toc-depth=3",
        "-o",
        str(out_pdf),
    ]
    run(cmd)


def merge_pdfs(pdfs: list[Path], out_pdf: Path):
    cmd = [PDFTK] + [str(p) for p in pdfs] + ["cat", "output", str(out_pdf)]
    run(cmd)


def gen_about(full_pdf: Path, out_pdf: Path, pages: int = 3):
    cmd = [PDFTK, str(full_pdf), "cat", f"1-{pages}", "output", str(out_pdf)]
    run(cmd)


def load_metadata(meta_path: Path) -> dict:
    if not meta_path.exists():
        print(f"⚠️  {meta_path} not found. Using defaults.")
        return {}
    return yaml.safe_load(meta_path.read_text()) or {}


def default_meta(src_docx: Path) -> dict:
    return {
        "title": src_docx.stem.replace("_", " "),
        "credits": "TBD",
        "credit_type": "TBD",
        "release_date": date.today().isoformat(),
        "expiration_date": "",
        "objectives": [],
        "disclaimer_html": "",
    }


def build_course(course_dir: Path):
    print(f"=== Building {course_dir.relative_to(REPO_ROOT)} ===")
    source_dir = course_dir / "source"
    gen_dir = course_dir / "generated"
    gen_dir.mkdir(exist_ok=True)

    # pick first DOCX that looks like the course body
    docxs = list(source_dir.glob("*.docx"))
    if not docxs:
        raise BuildError("No .docx files in source/")
    src_docx = docxs[0]

    fixed_docx = fix_headings(src_docx)

    meta = default_meta(src_docx)
    meta_path = course_dir / "metadata.yaml"
    meta.update(load_metadata(meta_path))

    # If no explicit cover_source_pdf in metadata, try heuristic using any PDF in source dir
    if "cover_source_pdf" not in meta:
        heuristic_pdf = next((p for p in source_dir.glob("*.pdf") if "final" in p.name.lower()), None)
        if heuristic_pdf:
            meta["cover_source_pdf"] = str(heuristic_pdf)

    cover_pdf = gen_dir / "cover.pdf"
    render_cover(meta, cover_pdf)

    # Apply overlay (text boxes) if overlay.json exists in course dir
    overlay_json = course_dir / "overlay.json"
    if overlay_json.exists():
        tmp_cover = gen_dir / "cover_with_overlay.pdf"
        apply_overlay(cover_pdf, overlay_json, meta, tmp_cover)
        cover_pdf = tmp_cover

    body_pdf_path = gen_dir / "body.pdf"
    body_pdf(fixed_docx, body_pdf_path)

    # Optional static pages (e.g., branding pages 2 and 3)
    extra_pages = []

    # --- Dynamic page2 rendered from templates/page2.html ---
    page2_html_tmpl = TEMPLATE_DIR / "page2.html"
    if page2_html_tmpl.exists():
        page2_pdf = gen_dir / "page2.pdf"
        # Render Jinja HTML -> PDF using WeasyPrint CLI (preferred) or python lib
        env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html"]))
        html_str = env.get_template("page2.html").render(**meta)
        try:
            # Homebrew CLI path first
            cli = Path("/opt/homebrew/bin/weasyprint")
            if cli.exists():
                with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
                    tmp.write(html_str)
                    tmp_path = tmp.name
                run([str(cli), tmp_path, str(page2_pdf)])
                Path(tmp_path).unlink(missing_ok=True)
            else:
                from weasyprint import HTML
                HTML(string=html_str, base_url=str(TEMPLATE_DIR)).write_pdf(str(page2_pdf))
        except Exception as exc:
            print("⚠️  Failed to render page2.html:", exc)
        else:
            extra_pages.append(page2_pdf)

    # --- Static page3 ---
    static_page3 = TEMPLATE_DIR / "static/page3.pdf"
    if static_page3.exists():
        extra_pages.append(static_page3)

    full_pdf = gen_dir / "full.pdf"
    merge_pdfs([cover_pdf, *extra_pages, body_pdf_path], full_pdf)

    about_pdf = gen_dir / "about.pdf"
    gen_about(full_pdf, about_pdf)

    print("✅ Build completed →", full_pdf)


def main():
    parser = argparse.ArgumentParser(description="Build a course (PDFs, etc.)")
    parser.add_argument("course", help="Path to course directory, e.g. courses/HIPAA-2024")
    args = parser.parse_args()

    build_course(Path(args.course).resolve())


if __name__ == "__main__":
    main() 