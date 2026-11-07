"""Every command of ``nightaudit`` through ``main()``: its output, its exit code and what it leaves on disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient
from nightaudit import cli
from nightaudit.cli import main
from nightkit import write_account

pytestmark = pytest.mark.integration


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str]:
    code = main(["run", str(write_account(tmp_path)), "--runs", str(tmp_path / "runs"), *extra])
    return code, capsys.readouterr().out


def test_run_prints_the_run_its_findings_and_its_hashes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(tmp_path, capsys, "--at", "2026-11-04T02:00:00Z")
    run_id = out.splitlines()[0].removeprefix("run ")
    assert code == 0
    assert (tmp_path / "runs" / run_id / "result.json").is_file()
    assert "  complete: True" in out
    assert "  findings: 3  informational: 0" in out
    assert "  billed total: 44.92" in out


def test_every_spelling_of_one_utc_instant_gives_the_same_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    control = write_account(tmp_path)
    spellings = [
        "2026-11-04T02:00:00Z",
        "2026-11-04T02:00:00+00:00",
        "2026-11-04T02:00:00",
        "2026-11-04T03:00:00+01:00",
    ]
    run_ids = set()
    for at in spellings:
        assert main(["run", str(control), "--runs", str(tmp_path / "runs"), "--at", at]) == 0
        run_ids.add(capsys.readouterr().out.splitlines()[0])
    assert len(run_ids) == 1


def test_a_run_with_a_missing_ledger_names_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    control = write_account(tmp_path)
    (tmp_path / "billed.csv").unlink()
    assert main(["run", str(control), "--runs", str(tmp_path / "runs"), "--at", "2026-11-04T02:00:00Z"]) == 0
    out = capsys.readouterr().out
    assert "  complete: False" in out
    assert "  missing ledgers: billed" in out
    assert "  findings: 0  informational: 0" in out


def test_a_run_time_that_is_not_iso_8601_is_refused_before_any_ledger_is_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(ValueError):
        _run(tmp_path, capsys, "--at", "4 Nov 2026")
    assert not (tmp_path / "runs").exists()


def test_verify_passes_a_fresh_pack_and_compares_the_page_beside_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = _run(tmp_path, capsys, "--at", "2026-11-04T02:00:00Z")
    run_id = out.splitlines()[0].removeprefix("run ")
    assert main(["verify", str(tmp_path / "runs" / run_id / "evidence")]) == 0
    assert capsys.readouterr().out.startswith("OK  ")


def test_verify_fails_a_pack_with_one_changed_byte(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out = _run(tmp_path, capsys, "--at", "2026-11-04T02:00:00Z")
    pack = tmp_path / "runs" / out.splitlines()[0].removeprefix("run ") / "evidence"
    chain = pack / "evidence.jsonl"
    chain.write_bytes(chain.read_bytes().replace(b"41.20", b"41.21", 1))
    assert main(["verify", str(pack)]) == 1
    assert capsys.readouterr().out.startswith("FAIL  ")


@pytest.mark.parametrize(
    ("beside", "message"),
    [("{not json", "cannot be read"), ("[1, 2, 3]", "is not a JSON object")],
)
def test_verify_fails_when_the_page_beside_the_pack_is_not_a_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], beside: str, message: str
) -> None:
    _, out = _run(tmp_path, capsys, "--at", "2026-11-04T02:00:00Z")
    run_dir = tmp_path / "runs" / out.splitlines()[0].removeprefix("run ")
    (run_dir / "result.json").write_text(beside, encoding="utf-8")
    assert main(["verify", str(run_dir / "evidence")]) == 1
    assert message in capsys.readouterr().out


def test_verify_fails_a_folder_that_holds_no_pack(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["verify", str(tmp_path)]) == 1
    assert capsys.readouterr().out.startswith("FAIL  ")


def test_serve_hands_uvicorn_an_app_that_answers_on_the_given_host_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    served: dict[str, Any] = {}

    def listen(app: Any, host: str, port: int) -> None:  # the network edge: no socket is opened
        served.update(app=app, host=host, port=port)

    monkeypatch.setattr(uvicorn, "run", listen)
    runs = tmp_path / "runs"
    assert main(["serve", "--app", "vampires", "--runs", str(runs), "--host", "0.0.0.0", "--port", "8123"]) == 0
    assert (served["host"], served["port"]) == ("0.0.0.0", 8123)
    assert TestClient(served["app"]).get("/api/health").json() == {"status": "ok"}
    assert runs.is_dir()


def test_serve_needs_an_app_name(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["serve"])
    assert exit_.value.code == 2
    assert "--app" in capsys.readouterr().err


def test_score_says_when_the_scorer_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    assert main(["score", "--set", "dev"]) == 1
    assert "Scorer not found" in capsys.readouterr().err


def test_score_runs_the_casebook_scorer_and_returns_its_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "score_casebook.py").write_text(
        "import sys\nsys.exit(0 if sys.argv[1:] == ['--set', 'dev', '--quiet'] else 3)\n", encoding="utf-8"
    )
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    assert main(["score", "--set", "dev", "--quiet"]) == 0
    assert main(["score", "--set", "dev"]) == 3


@pytest.mark.parametrize("argv", [[], ["unknown"], ["score", "--set", "other"]])
def test_an_unknown_command_or_choice_exits_with_usage(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(argv)
    assert exit_.value.code == 2
    assert "usage: nightaudit" in capsys.readouterr().err
