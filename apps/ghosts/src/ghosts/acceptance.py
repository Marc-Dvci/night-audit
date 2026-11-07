"""``python -m ghosts.acceptance``: run Hollow Pines and print the planted findings against the found ones.

``apps/ghosts/planted.yaml`` is the acceptance test and is never edited. As committed, it is not valid YAML: the story
of ``noor.haddad`` is a plain scalar containing ``? No:`` at the end of a line, which YAML reads as a mapping key.
``load_planted`` therefore quotes every ``story:`` value in memory before parsing. Only those free-text stories are
rewritten; keys, regions and counts are parsed as written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

import yaml
from nightaudit.models import LedgerName, RunResult

from .run import run
from .seats import seat_summary

APP_DIR = Path(__file__).resolve().parents[2]
PLANTED = APP_DIR / "planted.yaml"
CONTROL = APP_DIR / "controls" / "staff-access.yaml"
_STORY = re.compile(r"^(?P<indent>\s*)story:\s?(?P<text>.*)$")


def quote_stories(text: str) -> str:
    """Turn every ``story:`` value, with its continuation lines, into one double-quoted scalar."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        found = _STORY.match(lines[i])
        if not found:
            out.append(lines[i])
            i += 1
            continue
        indent = len(found.group("indent"))
        parts = [found.group("text").strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) > indent:
            parts.append(lines[i].strip())
            i += 1
        out.append(f"{found.group('indent')}story: {json.dumps(' '.join(p for p in parts if p))}")
    return "\n".join(out) + "\n"


def load_planted(path: Path = PLANTED) -> dict[str, Any]:
    """The planted findings, read without changing the file."""
    data: dict[str, Any] = yaml.safe_load(quote_stories(path.read_text(encoding="utf-8")))
    return data


@dataclass
class Verdict:
    """Planted against found, line by line."""

    rows: list[tuple[str, str, str, str]] = field(default_factory=list)  # key, planted, found, result
    checks: list[tuple[str, str, str, bool]] = field(default_factory=list)  # what, expected, actual, ok

    @property
    def ok(self) -> bool:
        return all(r[3] == "match" for r in self.rows) and all(c[3] for c in self.checks)


def compare(planted: dict[str, Any], result: RunResult, intended_count: int) -> Verdict:
    """Compare a run with the planted findings: same keys and regions, nothing extra, and the stated counts."""
    verdict = Verdict()
    names = result.region_names
    expected = {str(p["key"]): str(p["region"]) for p in planted["planted"]}
    found = {f.key: f.region_code for f in result.findings if not f.informational}
    for key in sorted(set(expected) | set(found), key=lambda k: (k not in expected, k)):
        want, got = expected.get(key), found.get(key)
        verdict.rows.append((
            key,
            f"{want} {names.get(want, '')}" if want else "(not planted)",
            f"{got} {names.get(got, '')}" if got else "(not found)",
            "match" if want == got else "MISMATCH",
        ))
    for p in planted["planted"]:
        if str(p["key"]) in found:
            name = names.get(str(p["region"]), "")
            verdict.checks.append((f"region name of {p['key']}", str(p["name"]), name, name == str(p["name"])))

    counts: dict[str, int] = {}
    for code in found.values():
        counts[code] = counts.get(code, 0) + 1
    want_counts = {str(k): int(v) for k, v in planted["expected_counts"].items()}
    verdict.checks.append(("finding counts by region", json.dumps(want_counts, sort_keys=True),
                           json.dumps(counts, sort_keys=True), counts == want_counts))

    summary = {v.vendor: v.unnamed_seats for v in seat_summary(result).vendors if v.unnamed_seats}
    want_unnamed = {str(u["vendor"]): int(u["quantity"]) for u in planted.get("unnamed_phantom_seats", [])}
    verdict.checks.append(("seats paid for nobody named", json.dumps(want_unnamed, sort_keys=True),
                           json.dumps(summary, sort_keys=True), summary == want_unnamed))
    unkeyed = [u for u in result.unkeyed if u.ledger == LedgerName.billed]
    verdict.checks.append(("unkeyed billed rows", str(sum(want_unnamed.values())), str(len(unkeyed)),
                           len(unkeyed) == sum(want_unnamed.values())))

    informational = sum(1 for f in result.findings if f.informational)
    minimum = int(planted.get("informational", {}).get("min_count", 0))
    verdict.checks.append(("Unlicensed users (IO), informational", f">= {minimum}", str(informational),
                           informational >= minimum))
    verdict.checks.append(("people on the HR roster on the run date", str(planted["staff_total"]),
                           str(intended_count), intended_count == int(planted["staff_total"])))
    verdict.checks.append(("pending keys", "0", str(len(result.pending_keys)), not result.pending_keys))
    verdict.checks.append(("run complete, no ledger errors", "True", str(result.complete and not result.ledger_errors),
                           result.complete and not result.ledger_errors))
    return verdict


def run_time_of(planted: dict[str, Any]) -> datetime:
    """The demo's run time: 02:00 UTC on the planted run date, as for Vampires."""
    return datetime.combine(datetime.fromisoformat(str(planted["run_date"])).date(), time(2, 0), tzinfo=UTC)


def evaluate(control: Path, runs: Path, planted: dict[str, Any]) -> tuple[RunResult, Verdict]:
    """Run *control* at the planted run time and compare."""
    result = run(control, runs, run_time_of(planted))
    intended = next((s for s in result.snapshots if s.name == LedgerName.intended), None)
    count = len({r.key for r in intended.records if r.key}) if intended else 0
    return result, compare(planted, result, count)


def table(verdict: Verdict) -> str:
    """The verdict as a Markdown table, then the checks."""
    lines = ["| Key | Planted | Found | Result |", "|---|---|---|---|"]
    lines += [f"| {k} | {p} | {f} | {r} |" for k, p, f, r in verdict.rows]
    lines += ["", "| Check | Planted | Found | Result |", "|---|---|---|---|"]
    lines += [f"| {w} | {e} | {a} | {'match' if ok else 'MISMATCH'} |" for w, e, a, ok in verdict.checks]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ghosts.acceptance", description=__doc__)
    parser.add_argument("--control", type=Path, default=CONTROL)
    parser.add_argument("--runs", type=Path, help="runs directory (default: a temporary folder)")
    args = parser.parse_args(argv)
    planted = load_planted()
    print(f"control {args.control}  run time {run_time_of(planted).isoformat()}")
    with tempfile.TemporaryDirectory() as scratch:
        result, verdict = evaluate(args.control, args.runs or Path(scratch), planted)
        print(f"run {result.run_id}  evidence chain {result.evidence_chain_hash}")
        print(table(verdict))
    print("ACCEPTED" if verdict.ok else "REJECTED")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
