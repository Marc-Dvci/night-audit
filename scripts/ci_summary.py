"""The CI job summary as Markdown: tests by kind, skips, decision core coverage per module and the casebook score.

    uv run python scripts/ci_summary.py --junit pytest.xml --coverage coverage.json --casebook casebook.log

Reads the files the test steps wrote and prints the tables; CI appends the output to ``$GITHUB_STEP_SUMMARY``. The
counts by kind come from collecting the suite once per marker expression, so they match what ``-m`` selects.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

#: Each kind and the marker expression that selects it. Unmarked tests are unit tests; every test is in one kind.
KINDS = [
    ("Unit", "not property and not integration and not e2e and not live and not lean"),
    ("Property", "property and not e2e"),
    ("Integration", "integration and not property and not e2e"),
    ("End-to-end (browser)", "e2e"),
    ("Live", "live"),
    ("Lean differential", "lean"),
]


def collected(expression: str) -> int:
    """How many tests ``-m expression`` selects, live tests included."""
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:randomly", "-m", expression]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    for line in reversed(done.stdout.splitlines()):
        words = line.split()
        if words and words[0].split("/")[0].isdigit() and ("selected" in line or "collected" in line):
            return int(words[0].split("/")[0])
    return 0


def junit_totals(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for name in totals:
            totals[name] += int(suite.get(name, 0))
    return totals


def skipped_reasons(path: Path) -> list[str]:
    reasons = []
    for case in ET.parse(path).getroot().iter("testcase"):
        skip = case.find("skipped")
        if skip is not None:
            reasons.append(f"`{case.get('classname')}.{case.get('name')}`: {skip.get('message', '')}")
    return reasons


def percent(covered: int, total: int) -> str:
    return "n/a" if total == 0 else f"{100 * covered / total:.1f}%"


def coverage_rows(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for name, file in sorted(data["files"].items()):
        s = file["summary"]
        module = "nightaudit." + Path(name).stem
        lines = percent(s["covered_lines"], s["num_statements"])
        branches = percent(s["covered_branches"], s["num_branches"])
        rows.append(f"| `{module}` | {lines} | {branches} | {s['missing_lines']} | {s['missing_branches']} |")
    t = data["totals"]
    rows.append(
        f"| **decision core** | **{percent(t['covered_lines'], t['num_statements'])}** "
        f"| **{percent(t['covered_branches'], t['num_branches'])}** | {t['missing_lines']} | {t['missing_branches']} |"
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--casebook", type=Path, required=True)
    parser.add_argument("--seed", default="")
    args = parser.parse_args()

    out = ["### Tests", ""]
    if args.junit.exists():
        totals = junit_totals(args.junit)
        passed = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
        out += [
            "| Ran | Passed | Failed | Errors | Skipped |",
            "|---|---|---|---|---|",
            f"| {totals['tests']} | {passed} | {totals['failures']} | {totals['errors']} | {totals['skipped']} |",
            "",
        ]
        out += [f"- skipped {reason}" for reason in skipped_reasons(args.junit)]
    if args.seed:
        out += ["", f"Random order: replay with `uv run pytest --randomly-seed={args.seed}`."]
    out += ["", "| Kind | Tests |", "|---|---|"]
    out += [f"| {kind} | {collected(expression)} |" for kind, expression in KINDS]
    out += ["", "### Decision core coverage", ""]
    if args.coverage.exists():
        out += ["| Module | Lines | Branches | Missing lines | Missing branches |", "|---|---|---|---|---|"]
        out += coverage_rows(args.coverage)
    out += ["", "### Casebook (development set)", ""]
    if args.casebook.exists():
        raw = args.casebook.read_bytes()
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
        lines = [line for line in text.splitlines() if line.strip()]
        score = lines[-1] if lines else "no output"
        out += ["| Set | Result |", "|---|---|", f"| dev | {score} |"]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
