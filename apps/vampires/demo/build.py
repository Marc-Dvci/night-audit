"""Run the three demo nights and export them as static files for the no-login demo.

Writes ``runs/demo`` (the API's runs folder) and ``skeleton/web/public/demo`` (runs.json, one JSON file per run and
the evidence pack of each run as a zip), which the UI reads when opened with ``?demo=1``.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from nightaudit.runner import load_run, run_control, run_summary

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = ROOT / "runs" / "demo"
STATIC = ROOT / "skeleton" / "web" / "public" / "demo"
NIGHTS = [
    ("night-1", datetime(2026, 11, 4, 2, 0, tzinfo=UTC)),
    ("night-2", datetime(2026, 11, 5, 2, 0, tzinfo=UTC)),
    ("night-3", datetime(2026, 11, 6, 2, 0, tzinfo=UTC)),
]


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
        result = load_run(RUNS, run_id)
        summaries.append(run_summary(result))
        (STATIC / f"{run_id}.json").write_text(result.model_dump_json(), encoding="utf-8")
        with zipfile.ZipFile(STATIC / f"evidence-{run_id}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ("evidence.jsonl", "manifest.json"):
                zf.write(RUNS / run_id / "evidence" / name, name)
    (STATIC / "runs.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"static demo written to {STATIC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
