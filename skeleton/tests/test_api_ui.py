"""API routes the UI kit reads, and the headers every response carries (ui-kit Req 4.1, 6.5, 7.2, 11.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nightaudit.api import CONTENT_SECURITY_POLICY, create_app
from nightaudit.evidence import verify_evidence_pack
from nightaudit.runner import run_control
from nightkit import RUN_TIME, write_account


@pytest.fixture()
def served(tmp_path: Path) -> tuple[TestClient, str, Path]:
    control = write_account(tmp_path)
    result = run_control(control, tmp_path / "runs", run_time=RUN_TIME)
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    return TestClient(create_app(tmp_path / "runs", static_dir=static)), result.run_id, tmp_path / "runs"


@pytest.mark.integration
def test_the_run_document_carries_the_view(served: tuple[TestClient, str, Path]) -> None:
    http, run_id, _ = served
    data = http.get(f"/api/runs/{run_id}").json()
    view = data["view"]
    assert view["headline"].startswith("1 Vampire exists and is on the bill with no approval: $41.20.")
    assert view["ledger_keys"] == {"intended": 2, "observed": 3, "billed": 2}
    assert (view["keyed_total"], view["unkeyed_total"], view["billed_total"]) == ("44.30", "0.62", "44.92")
    assert data["ui"]["columns"][0] == {"label": "Key", "from": "key"}


@pytest.mark.integration
def test_the_run_list_counts_new_findings(served: tuple[TestClient, str, Path]) -> None:
    http, _, _ = served
    assert http.get("/api/runs").json()[0]["new_findings"] == 3


@pytest.mark.integration
def test_the_evidence_files_are_served_as_written(served: tuple[TestClient, str, Path]) -> None:
    http, run_id, runs = served
    pack = runs / run_id / "evidence"
    jsonl = http.get(f"/api/runs/{run_id}/evidence.jsonl")
    assert jsonl.status_code == 200
    assert jsonl.headers["content-type"].startswith("application/x-ndjson")
    assert jsonl.content == (pack / "evidence.jsonl").read_bytes()
    manifest = http.get(f"/api/runs/{run_id}/manifest.json")
    assert manifest.json() == json.loads((pack / "manifest.json").read_text("utf-8"))
    assert manifest.json()["final_chain_hash"] == verify_evidence_pack(pack).final_hash


@pytest.mark.integration
def test_the_morning_report_is_served_with_its_own_policy(served: tuple[TestClient, str, Path]) -> None:
    http, run_id, _ = served
    report = http.get(f"/api/runs/{run_id}/report.html")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/html")
    assert "MORNING REPORT" in report.text
    policy = report.headers["content-security-policy"]
    assert policy.startswith("default-src 'none'; style-src 'sha256-")
    assert "script-src" not in policy


@pytest.mark.integration
@pytest.mark.parametrize("name", ["evidence.jsonl", "manifest.json", "report.html"])
def test_unknown_runs_are_not_found(served: tuple[TestClient, str, Path], name: str) -> None:
    http, _, _ = served
    assert http.get(f"/api/runs/{'0' * 16}/{name}").status_code == 404
    assert http.get(f"/api/runs/..%2F..%2Fetc/{name}").status_code == 404


@pytest.mark.integration
@pytest.mark.parametrize("path", ["/api/runs", "/api/health", "/", "/index.html", "/missing.js"])
def test_every_response_carries_the_security_headers(served: tuple[TestClient, str, Path], path: str) -> None:
    http, _, _ = served
    response = http.get(path)
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_the_policy_allows_only_the_same_origin() -> None:
    directives = dict(part.strip().split(" ", 1) for part in CONTENT_SECURITY_POLICY.split(";"))
    assert directives["default-src"] == "'none'"
    for name in ("script-src", "style-src", "font-src", "img-src", "connect-src"):
        assert directives[name] == "'self'"
    assert "unsafe-inline" not in CONTENT_SECURITY_POLICY
