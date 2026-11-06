"""Run the three demo nights and export them as static files for the no-login demo.

Writes ``runs/demo`` (the API's runs folder) and, under ``skeleton/web/public``:

* ``apps.json``: the apps this build offers (ui-kit Req 8.1): the live API and this recorded demo,
* ``demo/runs.json``: the run summaries, newest first,
* ``demo/<run id>/run.json``: the run as the page reads it (the result plus its ``view``),
* ``demo/<run id>/evidence.jsonl`` and ``manifest.json``: the evidence pack, for "Verify this night" (Req 6.5),
* ``demo/<run id>/report.html``: the morning report, marked as a recorded run (Req 7.2, 8.3),
* ``demo/<run id>/evidence.zip``: the pack as one download.

Rebuild: ``uv run python apps/vampires/demo/build.py``
"""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from nightaudit.api import run_document
from nightaudit.report import report_html
from nightaudit.runner import load_run, run_control, run_summary

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = ROOT / "runs" / "demo"
PUBLIC = ROOT / "skeleton" / "web" / "public"
STATIC = PUBLIC / "demo"
NIGHTS = [
    ("night-1", datetime(2026, 11, 4, 2, 0, tzinfo=UTC)),
    ("night-2", datetime(2026, 11, 5, 2, 0, tzinfo=UTC)),
    ("night-3", datetime(2026, 11, 6, 2, 0, tzinfo=UTC)),
]
APPS = [
    {"name": "vampires", "title": "Vampires", "mode": "live", "base": "api/"},
    {"name": "vampires-demo", "title": "Vampires demo account", "mode": "demo", "base": "demo/"},
]
#: A fixed zip timestamp, so a rebuild with the same inputs writes the same bytes.
ZIP_TIME = (2026, 11, 6, 2, 0, 0)


def export_run(run_id: str, out: Path) -> None:
    """Write one run's static files into *out*."""
    result = load_run(RUNS, run_id)
    out.mkdir(parents=True)
    (out / "run.json").write_text(json.dumps(run_document(result)), encoding="utf-8")
    (out / "report.html").write_text(report_html(result, recorded=True), encoding="utf-8")
    evidence = RUNS / run_id / "evidence"
    with zipfile.ZipFile(out / "evidence.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("evidence.jsonl", "manifest.json"):
            data = (evidence / name).read_bytes()
            (out / name).write_bytes(data)
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)


def main() -> int:
    shutil.rmtree(RUNS, ignore_errors=True)
    shutil.rmtree(STATIC, ignore_errors=True)
    STATIC.mkdir(parents=True)
    run_ids = []
    for folder, when in NIGHTS:
        result = run_control(HERE / folder / "control.yaml", RUNS, run_time=when)
        run_ids.append(result.run_id)
        print(f"{folder}: run {result.run_id}, {len(result.findings)} findings, pending {result.pending_keys}")
    summaries = []
    for run_id in reversed(run_ids):
        summaries.append(run_summary(load_run(RUNS, run_id)))
        export_run(run_id, STATIC / run_id)
    (STATIC / "runs.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    (PUBLIC / "apps.json").write_text(json.dumps(APPS, indent=2), encoding="utf-8")
    print(f"static demo written to {STATIC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
