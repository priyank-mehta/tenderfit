"""TenderFit web UI server."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parents[2]
ALLOWED_DIRS = {
    (BASE_DIR / "artifacts").resolve(),
    (BASE_DIR / "examples").resolve(),
    (BASE_DIR / "reports").resolve(),
    (BASE_DIR / "shortlists").resolve(),
}

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("tenderfit.web")
logger.debug("PATH=%s", os.environ.get("PATH", ""))
logger.debug("agent-browser=%s", shutil.which("agent-browser"))


class ScanRequest(BaseModel):
    keywords: str
    days: int = 14
    top: int = 30
    max_pages: int = 5
    llm_filter: bool = False
    llm_max_candidates: int = 100
    llm_batch_size: int = 5
    force_refresh: bool = False


class FetchRequest(BaseModel):
    bid_id: str
    out_dir: str | None = None
    cache_dir: str | None = None


class EvaluateRequest(BaseModel):
    bid_id: str
    company_path: str
    out_path: str | None = None


class ShortlistRequest(BaseModel):
    company_path: str
    top: int = 10
    out_path: str | None = None


@dataclass
class Job:
    job_id: str
    command: list[str]
    job_type: str
    status: str = "running"
    output_lines: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    events: "queue.Queue[dict[str, Any]]" = field(default_factory=queue.Queue)


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def create_job(self, command: list[str], job_type: str) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(job_id=job_id, command=command, job_type=job_type)
        with self.lock:
            self.jobs[job_id] = job
        logger.info("job.create id=%s type=%s cmd=%s", job_id, job_type, command)
        thread = threading.Thread(target=self._run_job, args=(job,), daemon=True)
        thread.start()
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def _run_job(self, job: Job) -> None:
        logger.info("job.start id=%s type=%s", job.job_id, job.job_type)
        job.events.put({"type": "status", "status": "running"})
        for stage in _initial_stages(job.job_type):
            job.events.put({"type": "stage", "stage": stage, "status": "running"})

        process = subprocess.Popen(
            job.command,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        logger.debug("job.exec id=%s pid=%s", job.job_id, process.pid)
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            if not line:
                continue
            job.output_lines.append(line)
            logger.debug("job.output id=%s line=%s", job.job_id, line)
            event = {"type": "log", "line": line}
            stage_event = _stage_event_from_line(line)
            if stage_event:
                job.events.put({"type": "stage", **stage_event})
            job.events.put(event)

        process.wait()
        job.finished_at = time.time()
        job.status = "completed" if process.returncode == 0 else "error"
        job.result = _extract_last_json(job.output_lines)
        if process.returncode != 0:
            job.error = f"command exited with {process.returncode}"
            logger.error("job.error id=%s returncode=%s", job.job_id, process.returncode)
        else:
            logger.info("job.done id=%s", job.job_id)
        job.events.put(
            {
                "type": "done" if job.status == "completed" else "error",
                "status": job.status,
                "result": job.result,
                "error": job.error,
            }
        )


def _extract_last_json(lines: Iterable[str]) -> dict[str, Any] | None:
    buffer: list[str] = []
    depth = 0
    started = False
    for line in reversed(list(lines)):
        if not line.strip() and not started:
            continue
        if not started and line.strip().endswith("}"):
            started = True
        if not started:
            continue
        buffer.append(line)
        depth += line.count("}")
        depth -= line.count("{")
        if started and depth <= 0:
            break
    if not buffer:
        logger.debug("json.extract empty")
        return None
    candidate = "\n".join(reversed(buffer))
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        logger.error("json.extract failed: %s", exc)
        return None


def _initial_stages(job_type: str) -> list[str]:
    if job_type == "scan":
        return ["scout"]
    if job_type == "fetch":
        return ["collector"]
    if job_type == "evaluate":
        return ["collector", "extractor", "verifier-a", "verifier-b", "verifier-c", "arbiter"]
    if job_type == "shortlist":
        return ["shortlist"]
    return []


def _stage_event_from_line(line: str) -> dict[str, Any] | None:
    if "collector.start" in line:
        return {"stage": "collector", "status": "running"}
    if "extractor.start" in line:
        return {"stage": "extractor", "status": "running"}
    if "verifier.start" in line:
        if "verifier_id=A" in line:
            return {"stage": "verifier-a", "status": "running"}
        if "verifier_id=B" in line:
            return {"stage": "verifier-b", "status": "running"}
        if "verifier_id=C" in line:
            return {"stage": "verifier-c", "status": "running"}
    if "arbiter.start" in line:
        return {"stage": "arbiter", "status": "running"}
    return None


def _safe_path(path: str) -> Path:
    resolved = (BASE_DIR / path).resolve()
    if not any(resolved.is_relative_to(allowed) for allowed in ALLOWED_DIRS):
        raise HTTPException(status_code=400, detail="Path not allowed.")
    return resolved


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
jobs = JobManager()


@app.get("/api/health")
def health() -> dict[str, str]:
    logger.debug("health.check")
    return {"status": "ok"}


@app.post("/api/jobs/scan")
def run_scan(payload: ScanRequest) -> JSONResponse:
    logger.info("api.scan payload=%s", payload.model_dump())
    cmd = [
        "python3",
        "-m",
        "tenderfit.cli",
        "scan",
        "--keywords",
        payload.keywords,
        "--days",
        str(payload.days),
        "--top",
        str(payload.top),
        "--max-pages",
        str(payload.max_pages),
    ]
    if payload.llm_filter:
        cmd.append("--llm-filter")
        cmd.extend(["--llm-max-candidates", str(payload.llm_max_candidates)])
        cmd.extend(["--llm-batch-size", str(payload.llm_batch_size)])
    if payload.force_refresh:
        cmd.append("--force-refresh")

    job = jobs.create_job(cmd, "scan")
    return JSONResponse({"job_id": job.job_id})


@app.post("/api/jobs/fetch")
def run_fetch(payload: FetchRequest) -> JSONResponse:
    logger.info("api.fetch payload=%s", payload.model_dump())
    if not payload.bid_id.strip():
        raise HTTPException(status_code=400, detail="bid_id is required.")
    out_dir = payload.out_dir or f"artifacts/{payload.bid_id}"
    cmd = [
        "python3",
        "-m",
        "tenderfit.cli",
        "fetch",
        "--bid-id",
        payload.bid_id,
        "--out",
        out_dir,
    ]
    if payload.cache_dir:
        cmd.extend(["--cache-dir", payload.cache_dir])

    job = jobs.create_job(cmd, "fetch")
    return JSONResponse({"job_id": job.job_id})


@app.post("/api/jobs/evaluate")
def run_evaluate(payload: EvaluateRequest) -> JSONResponse:
    logger.info("api.evaluate payload=%s", payload.model_dump())
    if not payload.bid_id.strip():
        raise HTTPException(status_code=400, detail="bid_id is required.")
    out_path = payload.out_path or f"reports/{payload.bid_id.replace('/', '-')}.md"
    cmd = [
        "python3",
        "-m",
        "tenderfit.cli",
        "evaluate",
        "--bid-id",
        payload.bid_id,
        "--company",
        payload.company_path,
        "--out",
        out_path,
    ]
    job = jobs.create_job(cmd, "evaluate")
    return JSONResponse({"job_id": job.job_id})


@app.post("/api/jobs/shortlist")
def run_shortlist(payload: ShortlistRequest) -> JSONResponse:
    logger.info("api.shortlist payload=%s", payload.model_dump())
    out_path = payload.out_path or "shortlists/shortlist.csv"
    cmd = [
        "python3",
        "-m",
        "tenderfit.cli",
        "shortlist",
        "--company",
        payload.company_path,
        "--top",
        str(payload.top),
        "--out",
        out_path,
    ]
    job = jobs.create_job(cmd, "shortlist")
    return JSONResponse({"job_id": job.job_id})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JSONResponse(
        {
            "job_id": job.job_id,
            "status": job.status,
            "result": job.result,
            "error": job.error,
        }
    )


@app.get("/api/jobs/{job_id}/events")
def stream_events(job_id: str) -> StreamingResponse:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    logger.info("events.stream id=%s type=%s", job_id, job.job_type)

    def event_stream() -> Iterable[str]:
        while True:
            try:
                event = job.events.get(timeout=1)
                yield f"data: {json.dumps(event, ensure_ascii=True)}\n\n"
                if event.get("type") in {"done", "error"}:
                    break
            except queue.Empty:
                if job.status in {"completed", "error"}:
                    break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/files")
def read_file(path: str) -> JSONResponse:
    resolved = _safe_path(path)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    if resolved.stat().st_size > 2_000_000:
        raise HTTPException(status_code=413, detail="File too large.")
    content = resolved.read_text(encoding="utf-8", errors="ignore")
    return JSONResponse({"path": str(resolved), "content": content})


def main() -> None:
    import uvicorn

    art = r"""
 _______ ______ _   _ _____  ______ _____  ______ _____ _______ 
|__   __|  ____| \ | |  __ \|  ____|  __ \|  ____|_   _|__   __|
   | |  | |__  |  \| | |  | | |__  | |__) | |__    | |    | |   
   | |  |  __| | . ` | |  | |  __| |  _  /|  __|   | |    | |   
   | |  | |____| |\  | |__| | |____| | \ \| |     _| |_   | |   
   |_|  |______|_| \_|_____/|______|_|  \_\_|    |_____|  |_|   
"""
    print(art)
    print("TenderFit Control Room starting at http://127.0.0.1:8000")

    uvicorn.run(
        "tenderfit.web.server:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
