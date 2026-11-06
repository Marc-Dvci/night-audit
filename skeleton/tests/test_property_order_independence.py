"""P2: record order does not change regions or amounts (Req 3.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hostile import RUN_TIME, controls, ledger_snapshots
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerSnapshot, RunResult


def _outcome(result: RunResult) -> tuple[dict[str, str], dict[str, Decimal], set[str], Decimal, Decimal]:
    billed = {code: s.billed_amount for code, s in result.region_summaries.items()}
    return result.regions, billed, set(result.pending_keys), result.billed_total, result.billed_unkeyed


@pytest.mark.property
@given(snapshots=ledger_snapshots(), control=controls(), data=st.data())
def test_property_shuffling_records_within_a_ledger_changes_no_region_and_no_amount(
    snapshots: list[LedgerSnapshot], control: ControlConfig, data: st.DataObject
) -> None:
    """P2 (Req 3.2): "For any three ledger snapshots, the set of key->region assignments and the billed amount per
    region are identical regardless of the order of records within each ledger."
    """
    shuffled = [
        s.model_copy(update={"records": data.draw(st.permutations(s.records), label=f"{s.name.value} order")})
        for s in snapshots
    ]
    assert _outcome(match(shuffled, control, RUN_TIME)) == _outcome(match(snapshots, control, RUN_TIME))
