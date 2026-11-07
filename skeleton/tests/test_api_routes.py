"""Every API route through the test client: what a caller reaches, what an unknown or hostile run id gets."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nightaudit.api import create_app
from nightaudit.runner import run_control
from nightkit import RUN_TIME, write_account

pytestmark = pytest.mark.integration

#: Every route that takes a run id, with the path after the id.
RUN_ROUTES = [
    "",
    "/findings",
    "/evidence.zip",
    "/evidence.jsonl",
    "/manifest.json",
    "/report.html",
    "/files/sheet.csv",
]

#: Run ids a caller can send that must never reach the file system as a path.
HOSTILE_IDS = [
    "..",
    "..%2F..%2Fetc%2Fpasswd",
    "%2e%2e",
    "0123456789ABCDEF",  # upper case is not a run id
    "0123456789abcde",  # fifteen characters
    "0123456789abcdef0",  # seventeen characters
    "0123456789abcdeg",
    "0123456789abcde%00",
    "_state",
    "0123456789abcdef%2F..",
]


@pytest.fixture()
def night(tmp_path: Path) -> tuple[TestClient, str, Path]:
    runs = tmp_path / "runs"
    result = run_control(write_account(tmp_path), runs, run_time=RUN_TIME)
    return TestClient(create_app(runs)), result.run_id, runs


def test_health_answers_ok_with_no_runs(tmp_path: Path) -> None:
    http = TestClient(create_app(tmp_path / "runs"))
    assert http.get("/api/health").json() == {"status": "ok"}


def test_an_empty_runs_folder_lists_no_runs_and_has_no_latest(tmp_path: Path) -> None:
    http = TestClient(create_app(tmp_path / "runs"))
    assert http.get("/api/runs").json() == []
    response = http.get("/api/latest")
    assert (response.status_code, response.json()["detail"]) == (404, "no runs yet")


def test_the_latest_run_is_the_newest_by_run_time_not_by_folder_name(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    control = write_account(tmp_path)
    later = run_control(control, runs, run_time=RUN_TIME.replace(day=6))
    earlier = run_control(control, runs, run_time=RUN_TIME)
    http = TestClient(create_app(runs))
    assert [r["run_id"] for r in http.get("/api/runs").json()] == [later.run_id, earlier.run_id]
    assert http.get("/api/latest").json()["run_id"] == later.run_id


def test_a_folder_with_an_unreadable_result_is_left_out_of_the_list(night: tuple[TestClient, str, Path]) -> None:
    http, run_id, runs = night
    (runs / "0000000000000000").mkdir()
    (runs / "0000000000000000" / "result.json").write_text("{not json", encoding="utf-8")
    assert [r["run_id"] for r in http.get("/api/runs").json()] == [run_id]


def test_a_run_document_carries_the_result_and_the_view(night: tuple[TestClient, str, Path]) -> None:
    http, run_id, _ = night
    document = http.get(f"/api/runs/{run_id}").json()
    assert document["run_id"] == run_id
    assert document["billed_total"] == "44.92"
    assert document["view"]["headline"]
    assert document["downloads"] == []


@pytest.mark.parametrize(
    ("region", "keys"),
    [
        (None, ["org-trail", "akiaexample0001", "i-0f3e"]),
        ("OB", ["i-0f3e"]),
        ("I", ["org-trail"]),
        ("IOB", []),  # matched keys are not findings
        ("XYZ", []),
    ],
)
def test_findings_are_filtered_by_region_code(
    night: tuple[TestClient, str, Path], region: str | None, keys: list[str]
) -> None:
    http, run_id, _ = night
    params = {"region": region} if region is not None else {}
    assert [f["key"] for f in http.get(f"/api/runs/{run_id}/findings", params=params).json()] == keys


def test_the_evidence_zip_holds_the_chain_and_the_manifest_as_written(night: tuple[TestClient, str, Path]) -> None:
    http, run_id, runs = night
    response = http.get(f"/api/runs/{run_id}/evidence.zip")
    assert response.headers["content-disposition"] == f"attachment; filename=evidence-{run_id}.zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == ["evidence.jsonl", "manifest.json"]
        assert archive.read("evidence.jsonl") == (runs / run_id / "evidence" / "evidence.jsonl").read_bytes()


@pytest.mark.parametrize(
    ("route", "media_type"),
    [("evidence.jsonl", "application/x-ndjson"), ("manifest.json", "application/json")],
)
def test_each_evidence_file_is_served_byte_for_byte(
    night: tuple[TestClient, str, Path], route: str, media_type: str
) -> None:
    http, run_id, runs = night
    response = http.get(f"/api/runs/{run_id}/{route}")
    assert response.headers["content-type"].startswith(media_type)
    assert response.content == (runs / run_id / "evidence" / route).read_bytes()


@pytest.mark.parametrize("route", ["/evidence.zip", "/evidence.jsonl", "/manifest.json"])
def test_a_run_whose_evidence_folder_is_gone_answers_404_for_its_evidence(
    night: tuple[TestClient, str, Path], route: str
) -> None:
    http, run_id, runs = night
    for file in (runs / run_id / "evidence").iterdir():
        file.unlink()
    (runs / run_id / "evidence").rmdir()
    assert http.get(f"/api/runs/{run_id}{route}").status_code == 404


def test_the_report_is_html_with_its_own_policy(night: tuple[TestClient, str, Path]) -> None:
    http, run_id, _ = night
    response = http.get(f"/api/runs/{run_id}/report.html")
    assert response.headers["content-type"].startswith("text/html")
    assert "script-src" not in response.headers["content-security-policy"]
    assert "i-0f3e" in response.text


@pytest.mark.parametrize("route", RUN_ROUTES)
def test_a_well_formed_run_id_that_does_not_exist_is_not_found(night: tuple[TestClient, str, Path], route: str) -> None:
    http, _, _ = night
    assert http.get(f"/api/runs/ffffffffffffffff{route}").status_code == 404


@pytest.mark.parametrize("route", RUN_ROUTES)
@pytest.mark.parametrize("run_id", HOSTILE_IDS)
def test_a_hostile_run_id_is_not_found_on_every_route(
    night: tuple[TestClient, str, Path], run_id: str, route: str
) -> None:
    http, _, _ = night
    response = http.get(f"/api/runs/{run_id}{route}")
    assert response.status_code == 404
    assert "root:" not in response.text


def test_the_state_folder_is_never_listed_as_a_run(night: tuple[TestClient, str, Path]) -> None:
    http, run_id, runs = night
    assert (runs / "_state").is_dir()
    assert [r["run_id"] for r in http.get("/api/runs").json()] == [run_id]


def test_an_unknown_api_path_is_not_found(night: tuple[TestClient, str, Path]) -> None:
    http, _, _ = night
    assert http.get("/api/nothing-here").status_code == 404


def test_the_static_front_end_is_served_from_the_same_origin(tmp_path: Path) -> None:
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Night Audit</title>", encoding="utf-8")
    http = TestClient(create_app(tmp_path / "runs", static_dir=static))
    page = http.get("/")
    assert (page.status_code, "<title>Night Audit</title>" in page.text) == (200, True)
    assert http.get("/api/health").json() == {"status": "ok"}  # the API wins over the static mount


def test_a_missing_static_folder_leaves_the_api_running(tmp_path: Path) -> None:
    http = TestClient(create_app(tmp_path / "runs", static_dir=tmp_path / "not-built"))
    assert http.get("/").status_code == 404
    assert http.get("/api/runs").json() == []


def test_a_listed_run_summary_counts_findings_and_informational_apart(night: tuple[TestClient, str, Path]) -> None:
    http, _, _ = night
    summary = http.get("/api/runs").json()[0]
    assert (summary["findings"], summary["informational"], summary["new_findings"], summary["complete"]) == (
        3,
        0,
        3,
        True,
    )


def test_the_report_of_the_night_after_a_finding_goes_lists_it_as_laid_to_rest_with_how_long_it_lasted(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    control = write_account(tmp_path)
    run_control(control, runs, run_time=RUN_TIME)
    intended = tmp_path / "intended.csv"
    intended.write_text(intended.read_text(encoding="utf-8") + "i3,i-0f3e\n", encoding="utf-8")  # now approved
    later = run_control(control, runs, run_time=RUN_TIME.replace(day=6))
    report = TestClient(create_app(runs)).get(f"/api/runs/{later.run_id}/report.html").text
    assert "Laid to rest" in report
    assert '<td class="key">i-0f3e</td><td>04 Nov 2026</td><td class="num">2 nights</td>' in report
