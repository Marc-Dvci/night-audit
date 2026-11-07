"""``python -m ghosts.run <control>``: run a control through the skeleton, then write the seat summary beside it.

The run itself is the skeleton's ``run_control``; this adds ``runs/<run_id>/seats.json`` (Req 4.3) and prints it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from nightaudit.models import RunResult
from nightaudit.runner import run_control

from .seats import seat_summary, summary_lines, write_seat_summary


def parse_run_time(text: str | None) -> datetime | None:
    """An ISO-8601 run time; naive values are UTC."""
    if text is None:
        return None
    parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def run(control: Path, runs: Path, run_time: datetime | None = None) -> RunResult:
    """Run *control* and write its seat summary. Returns the skeleton's result."""
    result = run_control(control, runs, run_time=run_time)
    write_seat_summary(result, runs / result.run_id)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ghosts.run", description=__doc__)
    parser.add_argument("control", help="path to the control YAML file")
    parser.add_argument("--runs", default="runs", help="runs directory (default: runs)")
    parser.add_argument("--at", help="ISO-8601 run time in UTC (default: now)")
    args = parser.parse_args(argv)
    result = run(Path(args.control), Path(args.runs), parse_run_time(args.at))
    findings = [f for f in result.findings if not f.informational]
    print(f"run {result.run_id}")
    print(f"  complete: {result.complete}")
    for ledger, error in sorted(result.ledger_errors.items()):
        print(f"  {ledger}: {error}")
    print(f"  findings: {len(findings)}  informational: {len(result.findings) - len(findings)}"
          f"  pending: {len(result.pending_keys)}")
    for finding in findings:
        print(f"    {finding.region_code:<3} {finding.name:<22} {finding.key}")
    print(f"  unkeyed billed rows: {sum(1 for u in result.unkeyed if u.ledger.value == 'billed')}")
    print(f"  billed total: {result.billed_total}")
    print("  seats:")
    for line in summary_lines(seat_summary(result)):
        print(f"    {line}")
    print(f"  evidence chain: {result.evidence_chain_hash}")
    return 0 if result.complete else 1


if __name__ == "__main__":
    sys.exit(main())
