"""Score the sealed held-out casebook. Run once per tagged release, never while developing.

    uv run python scripts/score_heldout.py

The held-out cases were written before any matcher code existed and are never used for tuning (audit rule 7).
Cases with a ``generator`` block are expanded here (``identical``: n keys present in all three ledgers, each ledger
shuffled with the given seed). Prints one line per case and the total; exits non-zero on any failure.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nightaudit.matcher import match  # noqa: E402
from score_casebook import build_control, build_snapshots, compare_result  # noqa: E402

CASEBOOK = Path(__file__).resolve().parents[1] / "casebook" / "heldout" / "cases.yaml"


def expand(case: dict[str, Any]) -> dict[str, Any]:
    gen = case.get("generator")
    if not gen:
        return case
    if gen.get("kind") != "identical":
        raise ValueError(f"unknown generator {gen}")
    rng = random.Random(int(gen.get("seed", 0)))
    keys = [f"i-{index:04x}" for index in range(int(gen["n"]))]
    ledgers: dict[str, list[dict[str, Any]]] = {}
    for ledger in ("intended", "observed", "billed"):
        order = keys[:]
        rng.shuffle(order)
        rows: list[dict[str, Any]] = []
        for i, key in enumerate(order):
            row: dict[str, Any] = {"row": f"{ledger[0]}{i}", "key": key}
            if ledger == "observed":
                row["ts"] = "2026-09-01T00:00:00Z"
            if ledger == "billed":
                row["amount"] = "1.00"
            rows.append(row)
        ledgers[ledger] = rows
    return {**case, "ledgers": ledgers}


def main() -> int:
    cases = yaml.safe_load(CASEBOOK.read_text(encoding="utf-8"))
    failed = 0
    for raw in cases:
        case = expand(raw)
        run_time = datetime.fromisoformat(str(case["now"]).replace("Z", "+00:00"))
        result = match(build_snapshots(case), build_control(case), run_time)
        problems = compare_result(result, case["expect"])
        print(f"{'PASS' if not problems else 'FAIL'}  {case['id']}")
        for problem in problems:
            print(f"      {problem}")
        failed += bool(problems)
    print(f"\n{len(cases) - failed} passed, {failed} failed, {len(cases)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
