"""Night-over-night state: new / persisting / resolved (Req 5.1-5.3).

A finding is identified by the pair ``(key, region_code)``.  State is persisted
per control (keyed by the control id) as a JSON file at
``runs/_state/<control_id>.json`` mapping ``"{key}:{region_code}"`` to
``{"first_seen": <iso-8601>, "region_code": <code>}``.

The state comparison depends only on the previous state file and the current
findings, both deterministic given the same inputs, so re-running with
identical inputs at the same ``run_time`` produces identical status
assignments (Req 5.3).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from .control import ControlConfig, resolve_region
from .models import INFORMATIONAL_REGIONS, Finding


def _utc_date(dt: datetime) -> date:
    """Return the calendar date of *dt* expressed in UTC."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.date()


def _nights_since(first_seen: datetime, run_time: datetime) -> int:
    """Number of midnights between *first_seen* and *run_time* (UTC date diff)."""
    return (_utc_date(run_time) - _utc_date(first_seen)).days


def _state_key(key: str, region_code: str) -> str:
    return f"{key}:{region_code}"


class FindingState(BaseModel):
    """One entry of the persisted state file."""

    first_seen: datetime
    region_code: str


class StateStore:
    """Load and save night-over-night state keyed by ``control_hash``."""

    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir

    def _path(self, control_id: str) -> Path:
        return self._runs_dir / "_state" / f"{control_id}.json"

    def load(self, control_hash: str) -> dict[str, FindingState]:
        """Return the previous state, or an empty dict when none exists."""
        path = self._path(control_hash)
        if not path.exists():
            return {}
        raw: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        result: dict[str, FindingState] = {}
        for key, value in raw.items():
            entry = value
            if isinstance(entry, dict):
                result[str(key)] = FindingState.model_validate(entry)
        return result

    def save(self, control_hash: str, state: dict[str, FindingState]) -> None:
        """Persist *state* to ``runs/<control_hash>/state.json``."""
        path = self._path(control_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.model_dump(mode="json") for k, v in state.items()}
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def compare_findings(
    current: list[Finding],
    previous: dict[str, FindingState],
    run_time: datetime,
    control: ControlConfig,
) -> tuple[list[Finding], list[Finding], dict[str, FindingState]]:
    """Compare current findings with the previous run's state.

    Returns a tuple ``(updated_findings, resolved_findings, new_state)`` where:

    - ``updated_findings`` are the current findings with ``status``,
      ``first_seen`` and ``nights_persisted`` set (Req 5.1-5.2).
    - ``resolved_findings`` are findings present in the previous run but absent
      now, reconstructed with ``status="resolved"`` (no current records).
    - ``new_state`` is the state to persist for the next run.
    """
    current_keys = {_state_key(f.key, f.region_code) for f in current}

    updated: list[Finding] = []
    new_state: dict[str, FindingState] = {}

    for finding in current:
        key = _state_key(finding.key, finding.region_code)
        if key in previous:
            first_seen = previous[key].first_seen
            nights = _nights_since(first_seen, run_time)
            updated.append(
                finding.model_copy(
                    update={
                        "status": "persisting",
                        "first_seen": first_seen,
                        "nights_persisted": nights,
                    }
                )
            )
        else:
            updated.append(
                finding.model_copy(
                    update={
                        "status": "new",
                        "first_seen": run_time,
                        "nights_persisted": 0,
                    }
                )
            )
        seen = updated[-1].first_seen
        new_state[key] = FindingState(
            first_seen=seen if seen is not None else run_time,
            region_code=finding.region_code,
        )

    resolved: list[Finding] = []
    for key in sorted(previous.keys() - current_keys):
        body, _, code = key.rpartition(":")
        name, severity, meaning = resolve_region(code, control)
        first_seen = previous[key].first_seen
        nights = _nights_since(first_seen, run_time)
        resolved.append(
            Finding(
                key=body,
                region_code=code,
                name=name,
                severity=severity,
                meaning=meaning,
                informational=code in INFORMATIONAL_REGIONS,
                status="resolved",
                first_seen=first_seen,
                nights_persisted=nights,
            )
        )

    return updated, resolved, new_state
