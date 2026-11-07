"""Connector contract tests. The Night Audit `add-control` skill copies this file to `tests/test_contracts.py`.

For every `controls/*.yaml` (not `*.live.yaml`) it checks that the file is a valid control, that every source is read-only,
and that every source loads its recorded fixture through its connector. These tests never run the matcher and never
open a network connection. Fixtures are scanned for values that look real (audit rule 9).
"""

from __future__ import annotations

import re
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from nightaudit.connectors import make_connectors
from nightaudit.models import LedgerName
from nightaudit.runner import load_control_file

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = sorted(p for p in (ROOT / "controls").glob("*.yaml") if not p.name.endswith(".live.yaml"))
LEDGERS = ("intended", "observed", "billed")
RUN_TIME = datetime(2026, 1, 1, tzinfo=UTC)

ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
ARN_ACCOUNT = re.compile(r"arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:(\d{12}):")
EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
EXAMPLE_ACCOUNTS = {"111122223333", "000000000000", "123456789012"}


def _example_domain(domain: str) -> bool:
    labels = domain.lower().split(".")
    return labels[-1] in {"test", "example", "invalid", "localhost"} or labels[-2].startswith("example")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a contract test must read recorded fixtures, never the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_there_is_a_control_to_test() -> None:
    assert CONTROLS, f"no controls/*.yaml in {ROOT}: write the control file before its contract tests"


@pytest.mark.parametrize("path", CONTROLS, ids=lambda p: p.name)
def test_control_declares_exactly_three_ledgers_with_known_normalisers(path: Path) -> None:
    load_control_file(path)  # raises on a missing or extra ledger, an unknown normaliser, or a bad field


@pytest.mark.parametrize("ledger", LEDGERS)
@pytest.mark.parametrize("path", CONTROLS, ids=lambda p: p.name)
def test_every_source_is_read_only(path: Path, ledger: str) -> None:
    control = load_control_file(path)
    connectors = make_connectors(LedgerName(ledger), control.ledgers[ledger], path.parent)
    assert connectors, f"{path.name}: the {ledger} ledger has no source"
    for connector in connectors:
        assert connector.read_only is True, f"{path.name}: {connector.source} is not read-only"


@pytest.mark.parametrize("ledger", LEDGERS)
@pytest.mark.parametrize("path", CONTROLS, ids=lambda p: p.name)
def test_every_source_loads_its_recorded_fixture_through_its_connector(path: Path, ledger: str) -> None:
    control = load_control_file(path)
    for connector in make_connectors(LedgerName(ledger), control.ledgers[ledger], path.parent):
        connector.bind_run_time(RUN_TIME)
        records = connector.fetch()
        assert records, f"{path.name}: {connector.source} gave no records; record a fixture with at least one row"
        assert all(r.ledger.value == ledger for r in records)
        assert any(r.raw_key.strip() for r in records), f"{connector.source}: no row has a value in the key field"
        row_ids = [r.row_id for r in records]
        assert len(set(row_ids)) == len(row_ids), f"{connector.source}: row ids must be unique within a source"


def test_fixtures_hold_only_example_or_redacted_values() -> None:
    problems: list[str] = []
    for file in sorted((ROOT / "fixtures").rglob("*")) if (ROOT / "fixtures").is_dir() else []:
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        name = file.relative_to(ROOT).as_posix()
        problems += [f"{name}: access key id {m}" for m in ACCESS_KEY.findall(text)]
        problems += [f"{name}: account id {a}" for a in ARN_ACCOUNT.findall(text) if a not in EXAMPLE_ACCOUNTS]
        problems += [f"{name}: email domain {d}" for d in EMAIL.findall(text) if not _example_domain(d)]
    assert not problems, "redact these before they are committed (use 111122223333 and example.test): " + "; ".join(
        sorted(set(problems))
    )
