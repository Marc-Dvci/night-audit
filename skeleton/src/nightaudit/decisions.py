"""Review decisions recorded against a run, and the check that lets the page show them (Req 10.7).

An application's review campaign (Ghosts' ``ghosts.review``) appends decisions to ``<run>/evidence/decisions.jsonl``.
Each row is canonical JSON with ``index``, ``prev_hash``, ``row_hash``, ``run_id``, ``evidence_chain_hash``, ``key``,
``region_code``, ``decision``, ``decision_date`` and ``reviewer``. The first ``prev_hash`` is the run's final evidence
chain hash and ``row_hash = SHA-256(prev_hash + canonical_json(row without row_hash))``, so every decision is bound to
the exact evidence it was made on.

This module only reads. The page shows decisions only when the whole chain verifies.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evidence import canonical_json, verify_evidence_pack
from .models import RunResult

DECISIONS_FILE = "decisions.jsonl"


@dataclass
class DecisionChain:
    """The verdict on a run's decisions, and the rows when they verify."""

    ok: bool
    detail: str
    failed_row: int | None = None
    count: int = 0
    head: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)


def decision_row_hash(row: dict[str, Any]) -> str:
    """The hash a decision row must carry."""
    content = {k: v for k, v in row.items() if k != "row_hash"}
    text = str(content.get("prev_hash", "")) + canonical_json(content)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pack_problem(run_dir: Path, result: RunResult) -> str | None:
    """Why the run's evidence pack cannot carry decisions, or ``None`` when it can."""
    pack = verify_evidence_pack(run_dir / "evidence")
    if not pack.ok:
        return f"the evidence pack of run {result.run_id} does not verify: {pack.detail}"
    if not result.evidence_chain_hash or pack.final_hash != result.evidence_chain_hash:
        return f"run {result.run_id} does not record the hash its evidence pack ends with"
    return None


def verify_decision_chain(
    run_dir: Path, result: RunResult, allowed: Collection[str] | None = None
) -> DecisionChain:
    """Check the evidence pack, then every decision: bytes, index, link, hash, binding, and the finding it names.

    ``allowed`` is the application's set of decisions; ``None`` accepts any non-empty decision.
    """
    problem = pack_problem(run_dir, result)
    if problem is not None:
        return DecisionChain(False, problem)
    findings = {f.key: f for f in result.findings if not f.informational}
    path = run_dir / "evidence" / DECISIONS_FILE
    if not path.exists():
        return DecisionChain(True, "evidence verifies; no decisions recorded", head=result.evidence_chain_hash)
    lines = path.read_bytes().split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    n = len(lines)
    prev = result.evidence_chain_hash
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(lines):
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return DecisionChain(False, f"decision {i}: not valid JSON", i, n)
        if not isinstance(row, dict):
            return DecisionChain(False, f"decision {i}: not a JSON object", i, n)
        if canonical_json(row).encode("utf-8") != raw:
            return DecisionChain(False, f"decision {i}: bytes differ from the canonical form", i, n)
        if row.get("index") != i:
            return DecisionChain(False, f"decision {i}: index is {row.get('index')!r}", i, n)
        if row.get("prev_hash") != prev:
            return DecisionChain(False, f"decision {i}: chain broken (prev_hash does not link)", i, n)
        if decision_row_hash(row) != row.get("row_hash"):
            return DecisionChain(False, f"decision {i}: hash mismatch", i, n)
        if row.get("run_id") != result.run_id or row.get("evidence_chain_hash") != result.evidence_chain_hash:
            return DecisionChain(False, f"decision {i}: bound to another run", i, n)
        finding = findings.get(str(row.get("key")))
        if finding is None or finding.region_code != row.get("region_code"):
            return DecisionChain(False, f"decision {i}: names a finding run {result.run_id} did not report", i, n)
        decision = row.get("decision")
        if not isinstance(decision, str) or not decision or (allowed is not None and decision not in allowed):
            return DecisionChain(False, f"decision {i}: unknown decision", i, n)
        prev = str(row["row_hash"])
        rows.append(row)
    return DecisionChain(True, f"evidence verifies; {n} decisions verify", count=n, head=prev, rows=rows)


def page_decisions(run_dir: Path, result: RunResult) -> dict[str, Any] | None:
    """What the page shows about decisions: ``None`` without a decision file, else the verdict and, if it holds, rows.

    A key decided twice shows its latest decision.
    """
    if not (run_dir / "evidence" / DECISIONS_FILE).exists():
        return None
    chain = verify_decision_chain(run_dir, result)
    latest: dict[str, dict[str, str]] = {}
    for row in chain.rows if chain.ok else []:
        latest[str(row["key"])] = {
            "key": str(row["key"]),
            "region_code": str(row.get("region_code", "")),
            "decision": str(row.get("decision", "")),
            "decision_date": str(row.get("decision_date", "")),
            "reviewer": str(row.get("reviewer", ""))[:200],
        }
    return {"ok": chain.ok, "detail": chain.detail, "rows": [latest[k] for k in sorted(latest)]}
