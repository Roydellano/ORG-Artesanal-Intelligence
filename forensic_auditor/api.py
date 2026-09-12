"""Local FastAPI service and optional built React static hosting."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .data import load_zip
from .demo import generate
from .investigation import Investigation, answer
from .reporting import export_case, printable

app = FastAPI(title="The Forensic Auditor", version="0.1.0")
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="auditor")
sessions = OrderedDict()
guard = threading.RLock()


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoRequest(StrictRequest):
    seed: int = Field(default=2026, ge=0, le=2**31 - 1)
    clean: bool = False


class StartRequest(StrictRequest):
    mode: Literal["offline", "ai"] = "offline"
    max_steps: int = Field(default=36, ge=1, le=60)
    seconds: int = Field(default=90, ge=5, le=120)


class QuestionRequest(StrictRequest):
    question: str = Field(min_length=1, max_length=1000)


def get_session(session_id: str):
    with guard:
        if session_id not in sessions:
            raise HTTPException(404, "Dataset session expired or was not found. Upload it again.")
        return sessions[session_id]


def register(content: bytes):
    try:
        data = load_zip(content)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    with guard:
        if len(sessions) >= 8:
            old = next((key for key, item in sessions.items() if not item["job"] or item["job"].snapshot()["status"] not in ("queued", "running")), None)
            if old is None:
                raise HTTPException(429, "All local dataset slots are busy.")
            del sessions[old]
        session_id = uuid4().hex
        sessions[session_id] = {"data": data, "job": None}
    return {"session_id": session_id, "dataset_id": data.identity,
            "coverage": {name: len(rows) for name, rows in data.tables.items()},
            "warnings": data.warnings, "files": list(data.files)}


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/datasets/demo")
def demo(body: DemoRequest):
    content, _ = generate(body.seed, body.clean)
    return register(content)


@app.get("/api/demo.zip")
def demo_download(seed: int = 2026, clean: bool = False):
    content, _ = generate(seed, clean)
    return Response(content, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="company-records.zip"'})


@app.post("/api/datasets/upload")
async def upload(file: UploadFile):
    try:
        content = await file.read(20_000_001)
        if len(content) > 20_000_000:
            raise HTTPException(413, "Upload limit is 20 MB")
        return register(content)
    finally:
        await file.close()


@app.post("/api/datasets/{session_id}/investigate")
def start(session_id: str, body: StartRequest):
    session = get_session(session_id)
    with guard:
        if session["job"] and session["job"].snapshot()["status"] in ("queued", "running"):
            raise HTTPException(409, "An investigation is already running.")
        active = sum(item["job"] is not None and item["job"].snapshot()["status"] in ("queued", "running") for item in sessions.values())
        if active >= 2:
            raise HTTPException(429, "Two investigations are already active. Wait or cancel one.")
        job = Investigation(session["data"], body.mode, body.max_steps, body.seconds)
        session["job"] = job
        pool.submit(job.run)
    return job.snapshot()


@app.get("/api/datasets/{session_id}/case")
def case_file(session_id: str):
    session = get_session(session_id)
    if not session["job"]:
        raise HTTPException(409, "Start an investigation first.")
    return session["job"].snapshot()


@app.post("/api/datasets/{session_id}/cancel")
def cancel(session_id: str):
    session = get_session(session_id)
    if session["job"]:
        session["job"].cancelled.set()
    return {"message": "Cancellation requested; any in-flight API call has a maximum 25-second timeout."}


@app.get("/api/datasets/{session_id}/records/{table}")
def records(session_id: str, table: str, offset: int = 0):
    data = get_session(session_id)["data"]
    if table not in data.tables or offset < 0:
        raise HTTPException(404, "Unknown table or invalid offset.")
    values = list(data.tables[table].values())
    return {"total": len(values), "rows": [{**row.model_dump(mode="json"), "evidence_id": f"{table}:{row.id}"} for row in values[offset:offset + 100]]}


@app.get("/api/datasets/{session_id}/evidence")
def evidence(session_id: str, ref: str):
    data = get_session(session_id)["data"]
    if ref not in data.evidence:
        raise HTTPException(404, "Evidence reference does not exist in this dataset.")
    return data.evidence[ref]


@app.post("/api/datasets/{session_id}/ask")
def ask(session_id: str, body: QuestionRequest):
    session = get_session(session_id)
    case = case_file(session_id)
    result = answer(case, body.question)
    session["data"].retrieve(result["evidence"])
    session["job"].event("case", "answer_question", {"question": body.question, **result})
    return result


@app.get("/api/datasets/{session_id}/export/{kind}")
def export(session_id: str, kind: Literal["json", "html"]):
    session = get_session(session_id)
    case = case_file(session_id)
    if kind == "html":
        return HTMLResponse(printable(session["data"], case), headers={"Content-Disposition": 'attachment; filename="case-file.html"'})
    return export_case(session["data"], case)


DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def index():
    if (DIST / "index.html").exists():
        return FileResponse(DIST / "index.html")
    return HTMLResponse("<h1>The Forensic Auditor API</h1><p>Start the React dev server or run npm run build in web/.</p><a href='/docs'>API documentation</a>")
