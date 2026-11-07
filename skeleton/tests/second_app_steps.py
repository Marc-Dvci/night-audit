"""Steps and a connector that the Req 10 tests name from control files as ``second_app_steps:<name>``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nightaudit.connectors import Connector
from nightaudit.models import Finding, LedgerName, Record, RunResult
from nightaudit.steps import ControlContext


def say(result: RunResult, options: dict[str, Any]) -> list[str]:
    """A summariser that returns the sentences its options hold."""
    return [str(s) for s in options.get("sentences", [])]


def count_billed(result: RunResult, options: dict[str, Any], control: ControlContext) -> list[str]:
    """A summariser that uses the control context and cites a number from the evidence."""
    return [f"Control {control.control_id} read its folder {control.folder.name}; amount {options['amount']}."]


def fail(result: RunResult, options: dict[str, Any]) -> list[str]:
    raise RuntimeError("summariser failed")


def not_a_list(result: RunResult, options: dict[str, Any]) -> Any:
    return "one sentence, not a list"


def where(findings: list[Finding], options: dict[str, Any], control: ControlContext) -> dict[str, dict[str, str]]:
    """An enricher that reports the control it was given."""
    aliases = ",".join(f"{k}>{v}" for k, v in sorted(control.alias_domains.items()))
    return {
        f.key: {
            "folder": control.folder.name,
            "aliases": aliases,
            "control_id": control.control_id,
            "run_date": control.run_time.date().isoformat() if control.run_time else "",
        }
        for f in findings
    }


def old_style(findings: list[Finding], options: dict[str, Any]) -> dict[str, dict[str, str]]:
    """An enricher written before Req 10.3: two arguments."""
    return {f.key: {"seen_by": "old_style"} for f in findings}


class DatedRows(Connector):
    """A connector that reads the run's date: one record keyed ``row-<run date>``."""

    def __init__(self, ledger: LedgerName, key_field: str = "", base_dir: Path | None = None, **_: Any) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> LedgerName:
        return self._ledger

    @property
    def read_only(self) -> bool:
        return True

    @property
    def source(self) -> str:
        return "dated"

    def fetch(self) -> list[Record]:
        day = self.run_time.date().isoformat() if self.run_time else "unbound"
        return [Record(ledger=self._ledger, source=self.source, row_id="1", raw_key=f"row-{day}")]


class Undated(DatedRows):
    """A connector written before Req 10.1, which never looks at the run time."""

    def fetch(self) -> list[Record]:
        return [Record(ledger=self._ledger, source=self.source, row_id="1", raw_key="row-fixed")]


class BreaksMidway(DatedRows):
    """A connector that reads two rows and then loses its source, as a network read does halfway through."""

    def fetch(self) -> list[Record]:
        rows = [Record(ledger=self._ledger, source=self.source, row_id=str(n), raw_key=f"row-{n}") for n in (1, 2)]
        if rows:
            raise ConnectionResetError("connection reset after 2 rows")
        return rows


class Writes(DatedRows):
    """A connector that does not declare itself read-only."""

    @property
    def read_only(self) -> bool:
        return False
