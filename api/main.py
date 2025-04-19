from fastapi import FastAPI, UploadFile, File, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from pathlib import Path
import yaml
import shutil
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import subprocess
import sys

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
COURSES_DIR = REPO_ROOT / "courses"

app = FastAPI()

# Allow front‑end served from same host/port (or any during dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # loosen during dev
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static front‑end at /ui/
app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")

# Serve course files (PDFs) for download
app.mount("/files", StaticFiles(directory=COURSES_DIR), name="files")

REPO_ROOT = REPO_ROOT
COURSES_DIR = COURSES_DIR
COURSES_DIR.mkdir(exist_ok=True)


class FrontMatterForm(BaseModel):
    title: Optional[str] = None
    credit_type: Optional[str] = None
    credits: Optional[float] = None
    release_date: Optional[str] = None  # ISO string
    expiration_date: Optional[str] = None
    objectives: List[str] = []
    disclaimer_html: Optional[str] = None
    cover_pages: Optional[int] = None


def load_meta(course_path: Path) -> dict:
    meta_path = course_path / "metadata.yaml"
    if meta_path.exists():
        return yaml.safe_load(meta_path.read_text()) or {}
    return {}


def save_meta(course_path: Path, meta: dict):
    meta_path = course_path / "metadata.yaml"
    meta_path.write_text(yaml.safe_dump(meta, sort_keys=False))


# ---------- SOURCE DOCX ----------


@app.post("/courses/{course_id}/source")
async def upload_source_docx(course_id: str, file: UploadFile = File(...)):
    if not file.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx accepted")
    course_path = COURSES_DIR / course_id
    source_dir = course_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    dest = source_dir / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"status": "ok", "saved": str(dest.relative_to(REPO_ROOT))}


# ---------- FRONT‑MATTER PDF ----------


@app.post("/courses/{course_id}/front-matter/file")
async def upload_front_matter_pdf(course_id: str, file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF accepted")
    course_path = COURSES_DIR / course_id
    source_dir = course_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    dest = source_dir / "front_matter.pdf"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    meta = load_meta(course_path)
    meta["cover_source_pdf"] = str(dest.relative_to(REPO_ROOT))
    meta.setdefault("cover_pages", 3)
    save_meta(course_path, meta)
    return {"status": "ok", "meta": meta}


# ---------- FRONT‑MATTER META ----------


@app.post("/courses/{course_id}/front-matter/meta")
async def save_front_matter_meta(course_id: str, data: FrontMatterForm):
    course_path = COURSES_DIR / course_id
    course_path.mkdir(parents=True, exist_ok=True)

    meta = load_meta(course_path)
    for k, v in data.dict(exclude_unset=True).items():
        meta[k] = v
    save_meta(course_path, meta)
    return {"status": "ok", "meta": meta}


# ---------- Legacy combined route (kept for compatibility) ----------

@app.post("/courses/{course_id}/front-matter")
async def set_front_matter(
    course_id: str,
    file: Optional[UploadFile] = File(None),
    data: Optional[FrontMatterForm] = None,
):
    course_path = COURSES_DIR / course_id
    source_dir = course_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    meta = load_meta(course_path)

    if file:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF accepted")
        dest = source_dir / "front_matter.pdf"
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        meta["cover_source_pdf"] = str(dest.relative_to(REPO_ROOT))
        meta.setdefault("cover_pages", 3)
    elif data:
        # Merge provided fields into metadata
        for k, v in data.dict(exclude_unset=True).items():
            meta[k] = v
    else:
        raise HTTPException(status_code=400, detail="Provide file or JSON data")

    save_meta(course_path, meta)
    return {"status": "ok", "meta": meta}


@app.get("/courses")
async def list_courses():
    return [p.name for p in COURSES_DIR.iterdir() if p.is_dir()]


# -------- Overlay JSON ----------


@app.get("/courses/{course_id}/overlay")
async def get_overlay(course_id: str):
    overlay_path = COURSES_DIR / course_id / "overlay.json"
    if overlay_path.exists():
        return json.loads(overlay_path.read_text())
    return {"fields": []}


@app.post("/courses/{course_id}/overlay")
async def save_overlay(course_id: str, payload: dict):
    course_dir = COURSES_DIR / course_id
    course_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = course_dir / "overlay.json"
    overlay_path.write_text(json.dumps(payload, indent=2))
    return {"status": "ok"}


# -------- Build Course ----------


@app.post("/courses/{course_id}/build")
async def build_course_endpoint(course_id: str):
    course_dir = COURSES_DIR / course_id
    if not course_dir.exists():
        raise HTTPException(status_code=404, detail="Course not found")
    try:
        result = subprocess.run([
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_course.py"),
            str(course_dir)
        ], capture_output=True, text=True, check=True)
        print(result.stdout)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"Build failed: {exc.stderr}")

    gen_dir = course_dir / "generated"
    artifacts = [str(p.relative_to(REPO_ROOT)) for p in gen_dir.glob("*.pdf")]
    return {"status": "ok", "artifacts": artifacts} 