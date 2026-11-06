"""FastAPI app serving JSON endpoints and a static front end (Req 8.1, ui-kit Req 6.5, 7.2, 11.2).

Endpoints:

* ``GET /api/runs``                         list of run summaries
* ``GET /api/runs/{id}``                    full ``RunResult`` as JSON, plus ``view`` (headline, counts, money lines)
* ``GET /api/runs/{id}/findings?region=``   findings filtered by region code
* ``GET /api/runs/{id}/evidence.zip``       the evidence pack as a zip file
* ``GET /api/runs/{id}/evidence.jsonl``     the evidence chain, for verification in the browser
* ``GET /api/runs/{id}/manifest.json``      the evidence manifest
* ``GET /api/runs/{id}/report.html``        the one-page morning report

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

from .models import Finding, RunResult
from .report import report_csp, report_html, run_view
from .runner import list_run_ids, load_run, run_summary

_RUN_ID = re.compile(r"^[0-9a-f]{16}$")

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


def run_document(result: RunResult) -> dict[str, Any]:
    """The run as the page reads it: the stored result plus the view computed by ``report.py``."""
    data = _as_json_dict(result)
    data["view"] = _as_json_dict(run_view(result))
    return data


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
        return run_document(_run_or_404(runs_dir, ids[0]))

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return run_document(_run_or_404(runs_dir, run_id))

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
