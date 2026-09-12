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
from .synthetic_records import records as demo_records
from .investigation import Investigation, answer
from .reporting import export_case, printable
from .privacy import Presentation
from openrouter_client import public_settings, chat, OpenRouterError

app = FastAPI(title="The Forensic Auditor", version="0.1.0")
from .official.api import router as official_router
app.include_router(official_router)


@app.middleware("http")
async def no_record_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="auditor")
sessions = OrderedDict()
guard = threading.RLock()


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoRequest(StrictRequest):
    seed: int = Field(default=2026, ge=0, le=2**31 - 1)
    clean: bool = False
    scenario: Literal["legacy", "all", "excess", "service", "return", "sale", "cycle"] = "all"


class StartRequest(StrictRequest):
    mode: Literal["offline", "ai"] = "offline"
    resume: bool = False
    max_steps: int = Field(default=60, ge=1, le=120)
    seconds: int = Field(default=90, ge=5, le=300)


class QuestionRequest(StrictRequest):
    question: str = Field(min_length=1, max_length=1000)


def get_session(session_id: str):
    with guard:
        if session_id not in sessions:
            raise HTTPException(404, "Dataset session expired or was not found. Upload it again.")
        return sessions[session_id]


def register(content: bytes, *, synthetic=False):
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
        presentation = Presentation(data)
        sessions[session_id] = {"data": data, "job": None, "synthetic": synthetic, "presentation": presentation}
    return {"session_id": session_id, "dataset_id": data.identity,
            "coverage": {name: len(rows) for name, rows in data.tables.items()},
            "warnings": presentation.apply(data.warnings), "files": list(data.files), "synthetic": synthetic}


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/config")
def config():
    return public_settings()


@app.post("/api/check-model")
def check_model():
    try:
        # Fixed, non-sensitive diagnostic; never includes uploaded records.
        chat([{"role": "user", "content": 'Return only JSON: {"ok":true}'}], synthetic=True)
        return {"ok": True, **public_settings()}
    except OpenRouterError as error:
        raise HTTPException(502, str(error)) from None


@app.post("/api/datasets/demo")
def demo(body: DemoRequest):
    content = demo_records(body.seed, body.scenario, body.clean)
    return register(content, synthetic=True)


@app.get("/api/demo.zip")
def demo_download(seed: int = 2026, clean: bool = False, scenario: Literal["legacy", "all", "excess", "service", "return", "sale", "cycle"] = "all"):
    content = demo_records(seed, scenario, clean)
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
    if body.mode == "ai":
        settings = public_settings()
        if not settings["configured"]:
            raise HTTPException(409, settings.get("error", "Set OPENROUTER_API_KEY in the server .env before starting AI mode."))
        if settings.get("synthetic_only") and not session["synthetic"]:
            raise HTTPException(409, "This free model is restricted to app-generated fictional demos. Uploaded records require offline review or no-collection/ZDR model routing.")
    with guard:
        if session["job"] and session["job"].snapshot()["status"] in ("queued", "running"):
            raise HTTPException(409, "An investigation is already running.")
        active = sum(item["job"] is not None and item["job"].snapshot()["status"] in ("queued", "running") for item in sessions.values())
        if active >= 2:
            raise HTTPException(429, "Two investigations are already active. Wait or cancel one.")
        if body.resume:
            job = session["job"]
            if job is None:
                raise HTTPException(409, "No incomplete investigation is available to resume.")
            try:
                job.prepare_resume(body.mode, seconds=body.seconds, max_steps=body.max_steps)
            except ValueError as error:
                raise HTTPException(409, str(error)) from None
        else:
            job = Investigation(session["data"], body.mode, body.max_steps, body.seconds, synthetic=session["synthetic"])
        session["job"] = job
        def execute():
            try:
                job.run()
            finally:
                with guard:
                    if session.get("deleting"):
                        job.cache.clear()
                        job.projection.clear()
                        sessions.pop(session_id, None)
        pool.submit(execute)
    return session["presentation"].apply(job.snapshot())


@app.get("/api/datasets/{session_id}/case")
def case_file(session_id: str, full: bool = False):
    session = get_session(session_id)
    if not session["job"]:
        raise HTTPException(409, "Start an investigation first.")
    result = session["job"].snapshot()
    return result if full else session["presentation"].apply(result)


@app.delete("/api/datasets/{session_id}")
def delete_dataset(session_id: str):
    session = get_session(session_id)
    with guard:
        job = session["job"]
        if job and job.snapshot()["status"] in ("queued", "running"):
            session["deleting"] = True
            job.cancelled.set()
            return {"status": "deleting", "message": "Cancellation requested; data will be released after the in-flight request ends."}
        if job:
            job.cache.clear()
            job.projection.clear()
        sessions.pop(session_id, None)
    return {"status": "deleted"}


@app.post("/api/datasets/{session_id}/cancel")
def cancel(session_id: str):
    session = get_session(session_id)
    if session["job"]:
        session["job"].cancelled.set()
    return {"message": "Cancellation requested; an in-flight request ends within its configured timeout (at most 60 seconds)."}


@app.get("/api/datasets/{session_id}/records/{table}")
def records(session_id: str, table: str, offset: int = 0):
    session = get_session(session_id)
    data = session["data"]
    if table not in data.tables or offset < 0:
        raise HTTPException(404, "Unknown table or invalid offset.")
    values = list(data.tables[table].values())
    return session["presentation"].apply({"total": len(values), "rows": [{**row.model_dump(mode="json"), "evidence_id": f"{table}:{row.id}"} for row in values[offset:offset + 100]]})


@app.get("/api/datasets/{session_id}/evidence")
def evidence(session_id: str, ref: str, reveal: bool = False):
    session = get_session(session_id)
    data = session["data"]
    ref = session["presentation"].reverse.get(ref, ref)
    if ref not in data.evidence and ":" in ref:
        table, record_alias = ref.split(":", 1)
        ref = f"{table}:{session['presentation'].reverse.get(record_alias, record_alias)}"
    if ref not in data.evidence:
        raise HTTPException(404, "Evidence reference does not exist in this dataset.")
    return data.evidence[ref] if reveal else session["presentation"].apply(data.evidence[ref])


@app.post("/api/datasets/{session_id}/ask")
def ask(session_id: str, body: QuestionRequest):
    session = get_session(session_id)
    case = case_file(session_id, full=True)
    session["presentation"].prepare(case)
    question = body.question
    for alias, original in session["presentation"].reverse.items():
        question = question.replace(alias, original)
    result = answer(case, question)
    session["data"].retrieve(result["evidence"])
    session["job"].event("case", "answer_question", {"question": body.question, **result})
    return session["presentation"].apply(result)


@app.get("/api/datasets/{session_id}/export/{kind}")
def export(session_id: str, kind: Literal["json", "html"], full: bool = False):
    session = get_session(session_id)
    case = case_file(session_id, full=True)
    if kind == "html":
        return HTMLResponse(printable(session["data"], case, full=full, presentation=session["presentation"]), headers={"Content-Disposition": 'attachment; filename="case-file.html"'})
    return export_case(session["data"], case, full=full, presentation=session["presentation"])


DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def index():
    if (DIST / "index.html").exists():
        return FileResponse(DIST / "index.html")
    return HTMLResponse("<h1>The Forensic Auditor API</h1><p>Start the React dev server or run npm run build in web/.</p><a href='/docs'>API documentation</a>")
