import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE = BASE_DIR / "storage"
UPLOADS = STORAGE / "uploads"
JOBS = STORAGE / "jobs"
CODEPACKS = Path(__file__).resolve().parent / "codepacks"

for p in (UPLOADS, JOBS):
    p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="CD Autopilot Web MVP")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def home():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def load_codepack(codepack_id: str) -> dict:
    if codepack_id == "wa-renton":
        fp = CODEPACKS / "wa_renton.json"
    else:
        raise HTTPException(400, "Unknown codepack")
    return json.loads(fp.read_text(encoding="utf-8"))


def write_artifact(job_dir: Path, name: str, content: str) -> Path:
    fp = job_dir / name
    fp.write_text(content, encoding="utf-8")
    return fp


def generate_mock_schedules(job_dir: Path):
    door_csv = "Mark,Type,Width,Height,Level,Remarks\nD1,EXT-SINGLE,3'-0\",6'-8\",MAIN,VERIFY\nD2,INT-SINGLE,2'-8\",6'-8\",MAIN,VERIFY\n"
    win_csv = "Mark,Type,Width,Height,Level,Remarks\nW1,CASEMENT,3'-0\",4'-0\",MAIN,EGRESS? VERIFY\nW2,FIXED,4'-0\",2'-0\",MAIN,TEMPERED? VERIFY\n"
    write_artifact(job_dir, "DOOR_SCHEDULE.csv", door_csv)
    write_artifact(job_dir, "WINDOW_SCHEDULE.csv", win_csv)


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    codepack: str = Form("wa-renton"),
    project_type: str = Form("residential_sfr"),
    instructions: str = Form(""),
):
    job_id = str(uuid.uuid4())
    job_dir = JOBS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_name = file.filename or "upload.bin"
    up_path = UPLOADS / f"{job_id}__{safe_name}"
    with up_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    cp = load_codepack(codepack)

    notes_lines = []
    notes_lines.append(f"PROJECT TYPE: {project_type}")
    notes_lines.append(f"CODEPACK: {cp['name']}")
    notes_lines.append("")
    notes_lines.append("GENERAL NOTES")
    for i, n in enumerate(cp["notes"]["general"], 1):
        notes_lines.append(f"{i}. {n}")
    notes_lines.append("")
    notes_lines.append("SITE NOTES")
    for i, n in enumerate(cp["notes"]["site"], 1):
        notes_lines.append(f"{i}. {n}")
    notes_lines.append("")
    notes_lines.append("PLAN NOTES")
    for i, n in enumerate(cp["notes"]["plan"], 1):
        notes_lines.append(f"{i}. {n}")
    notes_lines.append("")
    notes_lines.append("ROOF NOTES")
    for i, n in enumerate(cp["notes"]["roof"], 1):
        notes_lines.append(f"{i}. {n}")
    notes_lines.append("")
    notes_lines.append("STRUCTURAL COORDINATION")
    for i, n in enumerate(cp["notes"]["structural"], 1):
        notes_lines.append(f"{i}. {n}")

    if instructions.strip():
        notes_lines.append("")
        notes_lines.append("CLIENT / DESIGNER INSTRUCTIONS")
        notes_lines.append(instructions.strip())

    write_artifact(job_dir, "A112_NOTES.txt", "\n".join(notes_lines))
    generate_mock_schedules(job_dir)

    punch = [
        "PUNCHLIST (AUTO) — REVIEW REQUIRED",
        "1) Verify all Door/Window Marks match your plan tags.",
        "2) Verify egress window sizes for bedrooms (flagged 'EGRESS?').",
        "3) Verify tempered glazing at hazardous locations (flagged 'TEMPERED?').",
        "4) Confirm overall + key interior dimensions on A101–A103.",
        "5) Confirm roof pitches + gutters/downspouts notes on A106.",
        "6) Confirm sections show heights + insulation/vent notes.",
    ]
    write_artifact(job_dir, "PUNCHLIST.txt", "\n".join(punch))

    meta = {
        "job_id": job_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "complete",
        "summary": "Generated draft A112 notes + door/window schedules + punchlist (mock).",
        "upload": str(up_path.name),
        "codepack": codepack,
        "project_type": project_type,
        "artifacts": ["A112_NOTES.txt", "DOOR_SCHEDULE.csv", "WINDOW_SCHEDULE.csv", "PUNCHLIST.txt"],
    }
    (job_dir / "job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job_dir = JOBS / job_id
    meta_path = job_dir / "job.json"
    if not meta_path.exists():
        raise HTTPException(404, "Job not found")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    punch_preview = (job_dir / "PUNCHLIST.txt").read_text(encoding="utf-8")[:1200]
    return {
        "job_id": meta["job_id"],
        "status": meta["status"],
        "summary": meta["summary"],
        "artifacts": meta["artifacts"],
        "punchlist_preview": punch_preview,
    }


@app.get("/api/jobs/{job_id}/download/{artifact}")
def download(job_id: str, artifact: str):
    job_dir = JOBS / job_id
    fp = job_dir / artifact
    if not fp.exists():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(str(fp), filename=artifact)


@app.get("/api/codepacks")
def list_codepacks():
    return [{"id": "wa-renton", "name": "Renton, WA (starter pack)"}]
