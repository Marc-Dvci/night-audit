"""P5: billed amounts are conserved across regions and unkeyed lines (Req 3.5)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hostile import CLOUD, RUN_TIME, controls, exact_sum, key_of, ledger_snapshots, snapshot, surviving
from hypothesis import given
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record
from pydantic import ValidationError


@pytest.mark.property
@given(snapshots=ledger_snapshots(max_size=12), control=controls())
def test_property_region_billed_amounts_plus_unkeyed_equal_the_billed_total(
    snapshots: list[LedgerSnapshot], control: ControlConfig
) -> None:
    """P5 (Req 3.5): "For any run with at least one billed record, the sum of billed amounts over all regions plus the
    unkeyed billed amount equals the total billed amount, where the total is the sum of every surviving billed
    record's amount."

    Sums are compared exactly: a cent lost to rounding is a conservation failure.
    """
    billed = [r for r in surviving(snapshots, control) if r.ledger == LedgerName.billed and r.amount is not None]
    total = exact_sum(r.amount for r in billed if r.amount is not None)
    unkeyed = exact_sum(r.amount for r in billed if r.amount is not None and key_of(r, control) == "")

    result = match(snapshots, control, RUN_TIME)

    assert result.billed_total == total
    assert result.billed_unkeyed == unkeyed
    regions = [s.billed_amount for s in result.region_summaries.values()]
    assert exact_sum([*regions, result.billed_unkeyed]) == total
    for finding in result.findings:
        own = exact_sum(r.amount for r in finding.records if r.ledger == LedgerName.billed and r.amount is not None)
        assert finding.billed_amount == own, finding.key


@pytest.mark.parametrize("amount", ["NaN", "-NaN", "sNaN", "Infinity", "-Infinity"])
def test_a_record_refuses_a_non_finite_amount(amount: str) -> None:
    """Non-finite amounts cannot be summed or conserved, so ``Record`` rejects them and the generators omit them."""
    with pytest.raises(ValidationError):
        Record(ledger=LedgerName.billed, source="cur", row_id="b1", raw_key="i-0aa1", amount=Decimal(amount))


def test_regression_a_tiny_and_a_large_amount_on_one_key_are_added_without_rounding() -> None:
    """Shrunk from P5: ``1E-23 + 1E+5`` in the default 28-digit context gave ``100000.0000000000000000000000``."""
    billed = [
        Record(ledger=LedgerName.billed, source="cur-2026-11", row_id="1", raw_key="i-0aa1", amount=amount)
        for amount in (None, Decimal("1E-23"), Decimal("1E+5"))
    ]
    result = match(
        [snapshot(LedgerName.intended, []), snapshot(LedgerName.observed, []), snapshot(LedgerName.billed, billed)],
        CLOUD,
        RUN_TIME,
    )
    exact = Decimal("100000.00000000000000000000001")
    assert result.billed_total == exact
    assert result.region_summaries["B"].billed_amount == exact
    assert result.findings[0].billed_amount == exact
