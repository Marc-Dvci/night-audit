"""FastAPI app serving JSON endpoints and a static front end (Req 8.1, ui-kit Req 6.5, 7.2, 11.2).

Endpoints:

* ``GET /api/runs``                         list of run summaries
* ``GET /api/runs/{id}``                    full ``RunResult`` as JSON, plus ``view`` (headline, counts, money lines)
* ``GET /api/runs/{id}/findings?region=``   findings filtered by region code
* ``GET /api/runs/{id}/evidence.zip``       the evidence pack as a zip file
* ``GET /api/runs/{id}/evidence.jsonl``     the evidence chain, for verification in the browser
* ``GET /api/runs/{id}/manifest.json``      the evidence manifest
* ``GET /api/runs/{id}/notes.jsonl``        the investigator's notes chain, when the night shift wrote one
* ``GET /api/runs/{id}/report.html``        the one-page morning report
* ``GET /api/runs/{id}/files/{name}``       a download the control lists in ``ui.downloads`` (Req 10.6)

The static front end (Vite build output) is mounted at ``/`` when present, so the UI is served from the same origin.
Every response carries a Content-Security-Policy that allows only same-origin scripts, styles, fonts and images.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .decisions import page_decisions
from .models import DOWNLOAD_FILE, Finding, RunResult
from .notes import NOTES_FILE, page_notes
from .report import report_csp, report_html, run_view
from .runner import list_run_ids, load_run, run_summary

_RUN_ID = re.compile(r"^[0-9a-f]{16}$")
#: The media type of each allowed download type (``DOWNLOAD_FILE``).
DOWNLOAD_TYPES: dict[str, str] = {
    ".csv": "text/csv; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}

#: Same-origin only (ui-kit Req 11.2). The page has no inline script or style, so nothing else is needed.
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; "
    "connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def _run_or_404(runs_dir: Path, run_id: str) -> RunResult:
    if not _RUN_ID.match(run_id):
        raise HTTPException(status_code=404, detail="unknown run id")
    try:
        return load_run(runs_dir, run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found") from None


def _as_json_dict(model: Any) -> dict[str, Any]:
    """Serialise a pydantic model to a JSON-native dict (Decimal as string)."""
    data: dict[str, Any] = json.loads(model.model_dump_json())
    return data


def run_document(result: RunResult, run_dir: Path | None = None) -> dict[str, Any]:
    """The run as the page reads it: the stored result plus the view computed by ``report.py``.

    With the run's folder it also lists the downloads that exist there (Req 10.6) and the review decisions when the
    evidence folder holds a decision chain (Req 10.7), and the investigator's notes when it holds a notes chain
    (night shift Req 1.2).
    """
    data = _as_json_dict(result)
    data["view"] = _as_json_dict(run_view(result))
    data["downloads"] = (
        [{"label": d.label, "file": d.file} for d in result.ui.downloads if download_path(run_dir, result, d.file)]
        if run_dir is not None
        else []
    )
    decisions = page_decisions(run_dir, result) if run_dir is not None else None
    if decisions is not None:
        data["decisions"] = decisions
    notes = page_notes(run_dir, result) if run_dir is not None else None
    if notes is not None:
        data["investigator_notes"] = notes
    return data


def download_path(run_dir: Path, result: RunResult, name: str) -> Path | None:
    """The file a download names, or ``None``. Only a listed, allow-listed name of a regular file in the run's folder.

    Three independent checks, so no one mistake lets a request read another file (design §18.6): the name is listed in
    the run's own downloads, it matches the allow-list (no separator, no ``..``), and its resolved path sits directly
    in the run's folder.
    """
    if name not in {d.file for d in result.ui.downloads} or not DOWNLOAD_FILE.fullmatch(name):
        return None
    folder = run_dir.resolve()
    path = (run_dir / name).resolve()
    if path.parent != folder or not path.is_file():
        return None
    return path


def create_app(runs_dir: Path, static_dir: Path | None = None) -> FastAPI:
    """Build the Night Audit FastAPI app reading runs from *runs_dir*."""
    app = FastAPI(title="Night Audit", version="0.1.0")
    runs_dir.mkdir(parents=True, exist_ok=True)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)  # the report sets its own, stricter policy
        return response

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for run_id in list_run_ids(runs_dir):
            try:
                result = load_run(runs_dir, run_id)
            except FileNotFoundError:
                continue
            summaries.append(run_summary(result))
        return summaries

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/latest")
    def latest() -> dict[str, Any]:
        ids = list_run_ids(runs_dir)
        if not ids:
            raise HTTPException(status_code=404, detail="no runs yet")
        return run_document(_run_or_404(runs_dir, ids[0]), runs_dir / ids[0])

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return run_document(_run_or_404(runs_dir, run_id), runs_dir / run_id)

    @app.get("/api/runs/{run_id}/files/{name}")
    def get_download(run_id: str, name: str) -> FileResponse:
        result = _run_or_404(runs_dir, run_id)
        path = download_path(runs_dir / run_id, result, name)
        if path is None:
            raise HTTPException(status_code=404, detail="no such download")
        return FileResponse(
            path,
            media_type=DOWNLOAD_TYPES[path.suffix],
            headers={
                "Content-Disposition": f'attachment; filename="{path.name}"',
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    @app.get("/api/runs/{run_id}/findings")
    def get_findings(run_id: str, region: str | None = None) -> list[dict[str, Any]]:
        result = _run_or_404(runs_dir, run_id)
        findings: list[Finding] = result.findings
        if region is not None:
            findings = [f for f in findings if f.region_code == region]
        return [_as_json_dict(f) for f in findings]

    @app.get("/api/runs/{run_id}/evidence.zip")
    def get_evidence(run_id: str) -> StreamingResponse:
        _run_or_404(runs_dir, run_id)
        evidence_dir = runs_dir / run_id / "evidence"
        if not evidence_dir.exists():
            raise HTTPException(status_code=404, detail="evidence pack not found")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in ("evidence.jsonl", "manifest.json"):
                fpath = evidence_dir / fname
                if fpath.exists():
                    zf.write(fpath, fname)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=evidence-{run_id}.zip"},
        )

    def _evidence_file(run_id: str, name: str) -> Path:
        _run_or_404(runs_dir, run_id)
        path = runs_dir / run_id / "evidence" / name
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"{name} not found")
        return path

    @app.get("/api/runs/{run_id}/evidence.jsonl")
    def get_evidence_jsonl(run_id: str) -> FileResponse:
        return FileResponse(_evidence_file(run_id, "evidence.jsonl"), media_type="application/x-ndjson")

    @app.get("/api/runs/{run_id}/notes.jsonl")
    def get_notes_jsonl(run_id: str) -> FileResponse:
        return FileResponse(_evidence_file(run_id, NOTES_FILE), media_type="application/x-ndjson")

    @app.get("/api/runs/{run_id}/manifest.json")
    def get_manifest(run_id: str) -> FileResponse:
        return FileResponse(_evidence_file(run_id, "manifest.json"), media_type="application/json")

    @app.get("/api/runs/{run_id}/report.html")
    def get_report(run_id: str) -> HTMLResponse:
        result = _run_or_404(runs_dir, run_id)
        return HTMLResponse(report_html(result), headers={"Content-Security-Policy": report_csp()})

    if static_dir is not None and static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
