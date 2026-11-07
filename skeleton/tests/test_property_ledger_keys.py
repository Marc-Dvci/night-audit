"""P12: the ledger labels count keys, not rows (ui-kit Req 2.4, 2.5)."""

from __future__ import annotations

import pytest
from hostile import RUN_TIME, controls, key_of, ledger_snapshots, surviving
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record
from nightaudit.report import ledger_key_counts


@pytest.mark.property
@given(ledger_snapshots(), controls(), st.data())
def test_property_ledger_counts_are_distinct_keys(
    snapshots: list[LedgerSnapshot], control: ControlConfig, data: st.DataObject
) -> None:
    counts = ledger_key_counts(match(snapshots, control, RUN_TIME))
    for snapshot in snapshots:
        expected = {key_of(r, control) for r in surviving([snapshot], control)} - {""}
        assert counts[snapshot.name.value] == len(expected)

    # Repeating a row of an existing key, or adding a row with no key, changes no count.
    ledger = data.draw(st.sampled_from(list(LedgerName)))
    target = next(s for s in snapshots if s.name == ledger)
    extra: list[Record] = [r.model_copy(update={"row_id": r.row_id + "-again"}) for r in target.records[:1]]
    extra.append(
        Record(
            ledger=ledger,
            source="extra",
            row_id="no-key",
            raw_key="",
            attrs=dict(target.records[0].attrs) if target.records else {},
        )
    )
    grown = [s.model_copy(update={"records": [*s.records, *extra]}) if s.name == ledger else s for s in snapshots]
    assert ledger_key_counts(match(grown, control, RUN_TIME)) == counts


@pytest.mark.property
@given(ledger_snapshots(), controls(), st.sampled_from(list(LedgerName)))
def test_property_a_missing_ledger_counts_nothing(
    snapshots: list[LedgerSnapshot], control: ControlConfig, missing: LedgerName
) -> None:
    broken = [s.model_copy(update={"missing": True}) if s.name == missing else s for s in snapshots]
    counts = ledger_key_counts(match(broken, control, RUN_TIME))
    assert counts == {"intended": None, "observed": None, "billed": None}
