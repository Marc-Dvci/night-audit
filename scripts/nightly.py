"""Run `nightaudit run` for each control in apps/*/controls/. The `night-audit` Crew cron calls this.

    uv run python scripts/nightly.py [--runs runs] [--apps-dir apps]

`apps/*/controls/` also holds settings and exclusion files, so a file counts as a control only when its top level has
`ledgers`. Every control is run even when another fails. Exit code: 0 when every control ran, 1 when one raised.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from nightaudit.cli import main as nightaudit_main

ROOT = Path(__file__).resolve().parents[1]


def is_control(path: Path) -> bool:
    """True when *path* is a YAML mapping with a ``ledgers`` key."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and "ledgers" in data


def find_controls(apps_dir: Path) -> list[Path]:
    """Every control file under ``<apps_dir>/*/controls/``, in path order."""
    return [p for p in sorted(apps_dir.glob("*/controls/*.yaml")) if is_control(p)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", default="runs", help="runs folder (default: runs)")
    parser.add_argument("--apps-dir", type=Path, default=ROOT / "apps", help="apps folder (default: ./apps)")
    args = parser.parse_args(argv)
    controls = find_controls(args.apps_dir)
    if not controls:
        print(f"no controls found under {args.apps_dir}/*/controls/", file=sys.stderr)
        return 1
    failed = 0
    for control in controls:
        print(f"== {control}")
        try:
            nightaudit_main(["run", str(control), "--runs", args.runs])
        except Exception as exc:  # one control failing must not stop the others
            failed += 1
            print(f"FAILED {control.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
