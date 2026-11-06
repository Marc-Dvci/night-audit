"""Orchestrate one run end to end (design §13).

``run_control(control_path, runs_dir)`` loads a control file, fetches the three
ledgers via connectors (enforcing read-only, handling failures), runs the
match, applies night-over-night state, writes the evidence pack, generates
explanations, and persists the ``RunResult``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .connectors import Connector, make_connectors
from .control import ControlConfig, ControlFile, region_meanings, region_names, resolve_ui
from .evidence import write_evidence_pack
from .explain import ModelConfig, explain_finding
from .matcher import KeyScope, match
from .models import LedgerName, LedgerSnapshot, Record, RunResult
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
    connectors: list[Connector],
) -> tuple[LedgerSnapshot, str | None]:
    """Fetch one ledger from all its sources.

    Read-only is enforced per source (audit rule 3, Req 9.2). If any source fails, the ledger is
    missing for this run (Req 9.4) and the error is returned so the run can name it.
    """
    if not connectors:
        return (
            LedgerSnapshot(name=ledger_name, source=f"connector:{ledger_name.value}", missing=True),
            "no connector configured",
        )
    source = ", ".join(c.source for c in connectors)
    records: list[Record] = []
    for connector in connectors:
        if not connector.read_only:
            return (
                LedgerSnapshot(name=ledger_name, source=source, missing=True),
                f"{connector.source}: refused, connector is not read-only",
            )
        try:
            records.extend(connector.fetch())
        except Exception as exc:  # noqa: BLE001 - any connector failure makes the ledger missing
            return (
                LedgerSnapshot(name=ledger_name, source=source, missing=True),
                f"{connector.source}: {type(exc).__name__}: {str(exc)[:300]}",
            )
    return LedgerSnapshot(name=ledger_name, source=source, records=records), None


def _load_callable(entry: str) -> Any:
    module_name, _, attr = entry.partition(":")
    if not module_name or not attr:
        raise ValueError(f"entry '{entry}' must look like 'package.module:function'")
    return getattr(importlib.import_module(module_name), attr)


def load_exclusions(path: Path) -> frozenset[str]:
    """Read an exclusion file: a YAML list of keys, or a mapping with a ``keys`` list.

    Keys are compared after ``strip`` and ``lower``. A missing file means no exclusions.
    """
    if not path.exists():
        return frozenset()
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = raw.get("keys", []) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError(f"exclusion file {path} must hold a list of keys")
    return frozenset(str(item).strip().lower() for item in items if str(item).strip())


def load_scope(path: Path) -> KeyScope:
    """Read a scope file: a mapping with ``keys`` and ``prefixes`` lists, compared after ``strip`` and ``lower``."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"scope file {path} must hold a mapping with keys and prefixes")
    keys = frozenset(str(item).strip().lower() for item in raw.get("keys") or [] if str(item).strip())
    prefixes = tuple(str(item).strip().lower() for item in raw.get("prefixes") or [] if str(item).strip())
    return keys, prefixes


def run_control(
    control_path: Path,
    runs_dir: Path,
    run_time: datetime | None = None,
    model_config: ModelConfig | None = None,
) -> RunResult:
    """Run one control end to end and persist the result."""
    control_path = Path(control_path)
    base_dir = control_path.parent
    control_file = load_control_file(control_path)
    control_config: ControlConfig = control_file.to_config()
    control_id = control_file.id or control_path.stem
    now = run_time if run_time is not None else datetime.now(UTC)
    cfg = model_config if model_config is not None else ModelConfig()

    # Fetch ledgers via connectors (Req 9.1-9.4).
    snapshots: list[LedgerSnapshot] = []
    errors: dict[str, str] = {}
    for name in ("intended", "observed", "billed"):
        ledger_name = LedgerName(name)
        ledger_config = control_file.ledgers.get(name)
        connectors: list[Connector] = []
        if ledger_config is not None:
            try:
                connectors = make_connectors(ledger_name, ledger_config, base_dir)
            except (ValueError, ImportError) as exc:
                errors[name] = str(exc)
        snapshot, error = _fetch_snapshot(ledger_name, connectors)
        if error is not None and name not in errors:
            errors[name] = error
        snapshots.append(snapshot)

    exclusions: frozenset[str] = frozenset()
    if control_file.exclude_keys_file:
        exclusions = load_exclusions(base_dir / control_file.exclude_keys_file)

    scope: KeyScope | None = None
    if control_file.include_keys_file and (base_dir / control_file.include_keys_file).exists():
        scope = load_scope(base_dir / control_file.include_keys_file)

    result = match(snapshots, control_config, now, exclude_keys=exclusions, include=scope)
    # The run is identified by the whole control file (sources included), not only the matching rules.
    file_hash = control_file.canonical_hash()
    result.control_hash = file_hash
    result.run_id = hashlib.sha256(f"{now.isoformat()}:{file_hash}".encode()).hexdigest()[:16]
    result.control_id = control_id
    result.control_title = control_file.title
    result.app = control_file.app
    result.ledger_errors = errors
    result.ui = resolve_ui(control_file)
    result.region_names = region_names(control_config)
    result.region_meanings = region_meanings(control_config)

    # Night-over-night state, kept per control id so editing a control keeps its history (Req 5).
    state_store = StateStore(runs_dir)
    if result.complete:
        previous = state_store.load(control_id)
        updated, resolved, new_state = compare_findings(
            result.findings, previous, now, control_config
        )
        result.findings = updated
        result.resolved = resolved
        state_store.save(control_id, new_state)

    # Enrichers: read-only context for chosen regions. They cannot change a region (audit rule 1).
    for enricher in control_file.enrichers:
        targets = [f for f in result.findings if f.region_code in enricher.regions]
        if not targets:
            continue
        try:
            func = _load_callable(enricher.entry)
            context_by_key = func(targets, enricher.options)
        except Exception as exc:  # noqa: BLE001 - context is optional; the run keeps its findings
            result.ledger_errors[f"enricher:{enricher.entry}"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            continue
        for finding in result.findings:
            extra = context_by_key.get(finding.key)
            if extra:
                finding.context.update({str(k): str(v)[:500] for k, v in extra.items()})

    # Explanations (Req 7). Code has already decided every finding.
    for finding in result.findings:
        explanation = explain_finding(finding, cfg, control_config)
        finding.explanation = explanation.text

    # Evidence pack (Req 6.1): ledger rows and the findings they produce.
    run_dir = runs_dir / result.run_id
    write_evidence_pack(result, run_dir / "evidence")

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
    """Return the run ids that have a persisted result, newest run time first."""
    if not runs_dir.exists():
        return []
    ids: list[tuple[str, str]] = []
    for child in runs_dir.iterdir():
        result_file = child / "result.json"
        if not result_file.exists():
            continue
        try:
            run_time = str(json.loads(result_file.read_text(encoding="utf-8")).get("run_time", ""))
        except (OSError, ValueError):
            continue
        ids.append((run_time, child.name))
    ids.sort(reverse=True)
    return [run_id for _, run_id in ids]


def run_summary(result: RunResult) -> dict[str, Any]:
    """A compact summary for the ``/api/runs`` listing."""
    finding_count = sum(1 for f in result.findings if not f.informational)
    informational = sum(1 for f in result.findings if f.informational)
    new_findings = sum(1 for f in result.findings if not f.informational and f.status == "new")
    return {
        "run_id": result.run_id,
        "control_id": result.control_id,
        "control_title": result.control_title,
        "app": result.app,
        "run_time": result.run_time.isoformat(),
        "control_hash": result.control_hash,
        "complete": result.complete,
        "findings": finding_count,
        "new_findings": new_findings,
        "informational": informational,
    }
