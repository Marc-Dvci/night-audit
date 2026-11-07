"""The same inputs give the same bytes on every platform (audit rule 6, skeleton Req 5.3, 10.8).

A run's files and the static demo are evidence, and a test compares the committed demo with a fresh build. The first CI
run failed because Windows had written the committed files: ``Path.write_text`` turned each ``\\n`` of ``manifest.json``
into ``\\r\\n`` (and the zip carried that copy), ``ZipInfo`` recorded ``create_system = 0``, and git rewrote the CRLF of
a CSV. These tests need no Windows machine: ``windows_text.as_windows`` makes any platform write as Windows does.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from nightaudit.demo import export_run, write_runs_json
from nightaudit.evidence import verify_evidence_pack
from nightaudit.runner import run_control
from nightaudit.textfile import write_text_exact
from nightkit import RUN_TIME, write_account
from windows_text import as_windows

ROOT = Path(__file__).resolve().parents[2]
ZIP_TIME = (2026, 11, 4, 2, 0, 0)


def files(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def night(root: Path) -> tuple[Path, Path]:
    """Run the demo account and export it; return the runs folder and the export folder."""
    runs, out = root / "runs", root / "out"
    result = run_control(root / "control.yaml", runs, run_time=RUN_TIME)
    out.mkdir()
    export_run(runs, result.run_id, out / result.run_id, ZIP_TIME)
    write_runs_json(runs, [result.run_id], out)
    return runs, out


def test_a_run_and_its_export_have_the_same_bytes_when_the_platform_translates_newlines(tmp_path: Path) -> None:
    plain, windows = tmp_path / "plain", tmp_path / "windows"
    for root in (plain, windows):
        root.mkdir()
        write_account(root)
    plain_runs, plain_out = night(plain)
    with as_windows():
        windows_runs, windows_out = night(windows)

    assert files(windows_runs) == files(plain_runs)
    assert files(windows_out) == files(plain_out)
    assert any(name.endswith("result.json") for name in files(plain_runs))
    assert any(name.endswith("evidence.zip") for name in files(plain_out))


def test_no_file_of_a_run_holds_a_carriage_return_the_program_did_not_write(tmp_path: Path) -> None:
    write_account(tmp_path)
    with as_windows():
        runs, out = night(tmp_path)
    for folder in (runs, out):
        for name, data in files(folder).items():
            if not name.endswith(".zip"):
                assert b"\r" not in data, name


def test_the_zip_in_an_export_holds_the_manifest_as_written_and_names_no_platform(tmp_path: Path) -> None:
    write_account(tmp_path)
    with as_windows():
        runs, out = night(tmp_path)
    (run_id,) = [p.name for p in runs.iterdir() if p.name != "_state"]
    with zipfile.ZipFile(out / run_id / "evidence.zip") as archive:
        assert [i.filename for i in archive.infolist()] == ["evidence.jsonl", "manifest.json"]
        assert {i.create_system for i in archive.infolist()} == {3}
        for info in archive.infolist():
            assert archive.read(info) == (runs / run_id / "evidence" / info.filename).read_bytes()
    assert verify_evidence_pack(runs / run_id / "evidence").ok


def test_write_text_exact_keeps_each_line_ending_as_given(tmp_path: Path) -> None:
    path = tmp_path / "mixed.txt"
    with as_windows():
        write_text_exact(path, "unix\nwindows\r\nlast")
    assert path.read_bytes() == b"unix\nwindows\r\nlast"


def test_git_leaves_the_generated_demo_files_alone() -> None:
    """``* text=auto eol=lf`` would rewrite the CRLF of ``review.csv``; the demo is compared byte for byte."""
    rules = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "skeleton/web/public/demo/** -text" in rules
    assert "skeleton/web/public/apps.json -text" in rules
