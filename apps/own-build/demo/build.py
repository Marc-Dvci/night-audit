"""Run Night Audit over its own build for one night and export it as static files for the no-login demo.

The night is 2026-11-08 02:00 UTC, the first 02:00 after the recorded snapshot. The inputs are the four recorded
files in ``apps/own-build/data/``: the files the specs name and the files git tracks (both written by
``apps/own-build/snapshot.py`` for one commit), and Kiro's files and sessions exported from its own session store.
There is one night because there is one snapshot; nothing here pretends to a history.

This data is real: it holds no prompt and no reply: file paths, session ids,
model names, times and credits only.

The target is ``skeleton/web/public/demo/own-build/``; nothing else is written there.

Rebuild every demo: ``uv run python scripts/build_demos.py``. This app only: ``uv run python apps/own-build/demo/build.py``
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nightaudit.demo import export_run, replace_folder, write_runs_json
from nightaudit.runner import run_control
from nightaudit.wording import repo_app_words

HERE = Path(__file__).resolve().parent
APP_DIR = HERE.parent
ROOT = HERE.parents[2]
APP = "own-build"
CONTROL = APP_DIR / "controls" / "own-build.yaml"
RUNS = ROOT / "runs" / "own-build-demo"
DEMO_ROOT = ROOT / "skeleton" / "web" / "public" / "demo"
TARGET = DEMO_ROOT / APP
NIGHT = datetime(2026, 11, 8, 2, 0, tzinfo=UTC)
APP_ENTRIES = [{"name": "own-build-demo", "title": "Night Audit's own build", "mode": "demo", "base": f"demo/{APP}/"}]
#: A fixed zip timestamp, so a rebuild with the same inputs writes the same bytes.
ZIP_TIME = (2026, 11, 8, 2, 0, 0)
RUN_FILES = ("run.json", "report.html", "evidence.jsonl", "manifest.json", "evidence.zip")


def build(target: Path = TARGET, runs: Path = RUNS) -> list[str]:
    """Run the night into *runs*, export it into *target*; return the run ids."""
    replace_folder(runs, DEMO_ROOT, APP)
    replace_folder(target, DEMO_ROOT, APP)
    result = run_control(CONTROL, runs, run_time=NIGHT)
    findings = [f for f in result.findings if not f.informational]
    print(
        f"own-build {NIGHT.date()}: run {result.run_id}, {len(findings)} findings, "
        f"{len(result.findings) - len(findings)} informational, pending {result.pending_keys}"
    )
    export_run(runs, result.run_id, target / result.run_id, ZIP_TIME, words=repo_app_words(ROOT))
    write_runs_json(runs, [result.run_id], target)
    print(f"own-build demo written to {target}")
    return [result.run_id]


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
