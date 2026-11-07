"""Static demo export: the files the page reads for a recorded run, shared by every application (Req 10.8).

``export_run`` writes, into one folder per run: ``run.json`` (the result plus its view, downloads and verified
decisions), ``report.html`` (marked as recorded), ``evidence.jsonl`` and ``manifest.json``, ``evidence.zip`` with a
fixed time so a rebuild writes the same bytes, every download the control lists that exists beside the run, and
``decisions.jsonl`` when the run has one.

``replace_folder`` empties only the folder it is given, and refuses one that is not inside ``public/demo/<app>/`` or a
folder the caller passes as its own scratch space, so no application's build removes another's demo.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from .api import download_path, run_document
from .decisions import DECISIONS_FILE
from .report import report_html
from .runner import load_run, run_summary

ZipTime = tuple[int, int, int, int, int, int]


def export_run(runs: Path, run_id: str, out: Path, zip_time: ZipTime) -> None:
    """Write one run's static files into *out*."""
    result = load_run(runs, run_id)
    run_dir = runs / run_id
    out.mkdir(parents=True)
    (out / "run.json").write_text(json.dumps(run_document(result, run_dir)), encoding="utf-8")
    (out / "report.html").write_text(report_html(result, recorded=True), encoding="utf-8")
    evidence = run_dir / "evidence"
    with zipfile.ZipFile(out / "evidence.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("evidence.jsonl", "manifest.json"):
            data = (evidence / name).read_bytes()
            (out / name).write_bytes(data)
            info = zipfile.ZipInfo(name, date_time=zip_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    if (evidence / DECISIONS_FILE).exists():
        (out / DECISIONS_FILE).write_bytes((evidence / DECISIONS_FILE).read_bytes())
    for download in result.ui.downloads:
        source = download_path(run_dir, result, download.file)
        if source is not None:
            (out / download.file).write_bytes(source.read_bytes())


def write_runs_json(runs: Path, run_ids: list[str], target: Path) -> None:
    """``runs.json``: the summaries of *run_ids*, newest run time first."""
    summaries = sorted((run_summary(load_run(runs, r)) for r in run_ids), key=lambda s: s["run_time"], reverse=True)
    (target / "runs.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")


def replace_folder(target: Path, demo_root: Path, app: str) -> None:
    """Empty and recreate *target*, which must be ``demo_root/app`` or outside ``demo_root`` entirely.

    A target inside ``demo_root`` that is not this app's own folder (another app's, or ``demo_root`` itself) is
    refused, so one build can never delete another app's demo.
    """
    target, root = target.resolve(), demo_root.resolve()
    if target != root / app and (target == root or root in target.parents):
        raise ValueError(f"{app} may only write {root / app}, not {target}")
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
