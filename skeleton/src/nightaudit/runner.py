"""Orchestrate one run end to end (design §13).

``run_control(control_path, runs_dir)`` loads a control file, fetches the three
ledgers via connectors (enforcing read-only, handling failures), runs the
match, applies night-over-night state, writes the evidence pack, generates
explanations, and persists the ``RunResult``.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .connectors import Connector, make_connector
from .control import ControlConfig, ControlFile
from .evidence import write_evidence_pack
from .explain import ModelConfig, explain_finding
from .matcher import match
from .models import LedgerName, LedgerSnapshot, RunResult
from .state import StateStore, compare_findings


def load_control_file(control_path: Path) -> ControlFile:
    """Parse and validate a control file (Req 1.1-1.3)."""
    raw: dict[str, Any] = yaml.safe_load(control_path.read_text(encoding="utf-8"))
    control = ControlFile.model_validate(raw)
    control.validate_ledgers()
    control.validate_normalisers()
    return control


def _fetch_snapshot(
    ledger_name: LedgerName,
    connector: Connector | None,
) -> LedgerSnapshot:
    """Fetch one ledger, enforcing read-only and treating failure as missing (Req 9)."""
    fallback_source = f"connector:{ledger_name.value}"
    if connector is None:
        return LedgerSnapshot(name=ledger_name, source=fallback_source, missing=True)
    if not connector.read_only:
        # Refuse to run a non-read-only connector (audit rule 3, Req 9.2).
        return LedgerSnapshot(name=ledger_name, source=connector.source, missing=True)
    try:
        records = connector.fetch()
    except (OSError, ValueError, KeyError, csv.Error):
        return LedgerSnapshot(name=ledger_name, source=connector.source, missing=True)
    return LedgerSnapshot(
        name=ledger_name,
        source=connector.source,
        records=records,
        missing=False,
    )


def run_control(
    control_path: Path,
    runs_dir: Path,
    run_time: datetime | None = None,
    model_config: ModelConfig | None = None,
) -> RunResult:
    """Run one control end to end and persist the result."""
    control_file = load_control_file(control_path)
    control_config: ControlConfig = control_file.to_config()
    control_hash = control_file.canonical_hash()
    now = run_time if run_time is not None else datetime.now(timezone.utc)
    cfg = model_config if model_config is not None else ModelConfig()

    # Fetch ledgers via connectors (Req 9.1-9.4).
    snapshots: list[LedgerSnapshot] = []
    for name in ("intended", "observed", "billed"):
        ledger_name = LedgerName(name)
        ledger_config = control_file.ledgers.get(name)
        connector: Connector | None = None
        if ledger_config is not None:
            try:
                connector = make_connector(ledger_name, ledger_config)
            except ValueError:
                connector = None
        snapshots.append(_fetch_snapshot(ledger_name, connector))

    result = match(snapshots, control_config, now)

    # Night-over-night state (Req 5.1-5.3).
    state_store = StateStore(runs_dir)
    if result.complete:
        previous = state_store.load(control_hash)
        updated, resolved, new_state = compare_findings(
            result.findings, previous, now, control_config
        )
        result.findings = updated
        result.resolved = resolved
        state_store.save(control_hash, new_state)

    # Evidence pack (Req 6.1).
    run_dir = runs_dir / result.run_id
    write_evidence_pack(result, run_dir / "evidence")

    # Explanations (Req 7).
    for finding in result.findings:
        explanation = explain_finding(finding, cfg, control_config)
        finding.explanation = explanation.text

    # Persist the RunResult.
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    return result


def load_run(runs_dir: Path, run_id: str) -> RunResult:
    """Load a persisted ``RunResult`` from ``runs/<run_id>/result.json``."""
    return RunResult.model_validate_json(
        (runs_dir / run_id / "result.json").read_text(encoding="utf-8")
    )


def list_run_ids(runs_dir: Path) -> list[str]:
    """Return the run ids that have a persisted result, newest-first by mtime."""
    if not runs_dir.exists():
        return []
    ids: list[tuple[float, str]] = []
    for child in runs_dir.iterdir():
        if (child / "result.json").exists():
            ids.append((child.stat().st_mtime, child.name))
    ids.sort(key=lambda pair: pair[0], reverse=True)
    return [run_id for _, run_id in ids]


def run_summary(result: RunResult) -> dict[str, Any]:
    """A compact summary for the ``/api/runs`` listing."""
    finding_count = sum(1 for f in result.findings if not f.informational)
    informational = sum(1 for f in result.findings if f.informational)
    return {
        "run_id": result.run_id,
        "run_time": result.run_time.isoformat(),
        "control_hash": result.control_hash,
        "complete": result.complete,
        "findings": finding_count,
        "informational": informational,
    }
