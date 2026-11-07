"""Run Hollow Pines on its fixed run date and export it as static files for the no-login demo (Req 7.2).

Writes the same files per run as ``apps/vampires/demo/build.py``:

* ``runs.json``: the run summaries, newest first,
* ``<run id>/run.json``: the run as the page reads it (the result plus its ``view``),
* ``<run id>/evidence.jsonl`` and ``manifest.json``: the evidence pack, for "Verify this night",
* ``<run id>/report.html``: the morning report, marked as a recorded run,
* ``<run id>/evidence.zip``: the pack as one download (fixed zip time),
* ``<run id>/seats.json``: the seat summary written beside the run (Req 4.3),

and ``apps.entry.json``, the entry to add to ``skeleton/web/public/apps.json`` (base ``demo/ghosts/``).

The intended target is ``skeleton/web/public/demo/ghosts/``. The app builder may not write under ``skeleton/``, so the
default target is ``apps/ghosts/demo/out/``; ``--public`` writes to the intended target for whoever may.

Rebuild: ``uv run python apps/ghosts/demo/build.py``
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from ghosts.run import run
from nightaudit.api import run_document
from nightaudit.report import report_html
from nightaudit.runner import load_run, run_summary

HERE = Path(__file__).resolve().parent
APP = HERE.parent
ROOT = HERE.parents[2]
CONTROL = APP / "controls" / "staff-access.yaml"
RUNS = ROOT / "runs" / "ghosts-demo"
OUT = HERE / "out"
PUBLIC = ROOT / "skeleton" / "web" / "public" / "demo" / "ghosts"
RUN_TIME = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)
APP_ENTRY = {"name": "ghosts-demo", "title": "Hollow Pines demo company", "mode": "demo", "base": "demo/ghosts/"}
#: A fixed zip timestamp, so a rebuild with the same inputs writes the same bytes.
ZIP_TIME = (2026, 11, 4, 2, 0, 0)
RUN_FILES = ("run.json", "report.html", "evidence.jsonl", "manifest.json", "evidence.zip", "seats.json")


def export_run(runs: Path, run_id: str, out: Path) -> None:
    """Write one run's static files into *out*."""
    result = load_run(runs, run_id)
    out.mkdir(parents=True)
    (out / "run.json").write_text(json.dumps(run_document(result)), encoding="utf-8")
    (out / "report.html").write_text(report_html(result, recorded=True), encoding="utf-8")
    (out / "seats.json").write_bytes((runs / run_id / "seats.json").read_bytes())
    evidence = runs / run_id / "evidence"
    with zipfile.ZipFile(out / "evidence.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("evidence.jsonl", "manifest.json"):
            data = (evidence / name).read_bytes()
            (out / name).write_bytes(data)
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)


def build(target: Path = OUT, runs: Path = RUNS) -> str:
    """Run the control into *runs*, export it into *target*, and return the run id."""
    shutil.rmtree(runs, ignore_errors=True)
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    result = run(CONTROL, runs, RUN_TIME)
    findings = [f for f in result.findings if not f.informational]
    print(f"run {result.run_id}: {len(findings)} findings, {len(result.findings) - len(findings)} informational, "
          f"pending {result.pending_keys}")
    export_run(runs, result.run_id, target / result.run_id)
    summaries = [run_summary(load_run(runs, result.run_id))]
    (target / "runs.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    (target / "apps.entry.json").write_text(json.dumps(APP_ENTRY, indent=2) + "\n", encoding="utf-8")
    print(f"static demo written to {target}")
    return result.run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the recorded Hollow Pines demo.")
    parser.add_argument("--public", action="store_true", help=f"write to {PUBLIC} instead of {OUT}")
    args = parser.parse_args(argv)
    build(PUBLIC if args.public else OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
