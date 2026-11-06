"""P13: money is shown exactly (ui-kit Req 3.1-3.3)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hostile import RUN_TIME, amounts, controls, exact_sum, ledger_snapshots
from hypothesis import given
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerSnapshot
from nightaudit.report import money_text, run_view


def parse_money(text: str) -> Decimal:
    negative = text.startswith("\u2212")
    body = text.removeprefix("\u2212")
    assert body.startswith("$")
    value = Decimal(body[1:].replace(",", ""))
    return value.copy_negate() if negative else value  # unary minus would round to 28 digits


@pytest.mark.property
@given(amounts())
def test_property_money_text_shows_the_exact_amount(value: Decimal) -> None:
    text = money_text(value)
    assert parse_money(text) == value
    fraction = text.rsplit(".", 1)[1]
    assert len(fraction) >= 2 and fraction.isdigit()
    assert text.startswith("\u2212") == (value < 0)
    whole = text.removeprefix("\u2212")[1:].split(".")[0]
    assert all(len(group) == 3 for group in whole.split(",")[1:])


@pytest.mark.property
@given(ledger_snapshots(), controls())
def test_property_keyed_and_unkeyed_totals_add_up_to_the_bill(
    snapshots: list[LedgerSnapshot], control: ControlConfig
) -> None:
    view = run_view(match(snapshots, control, RUN_TIME))
    assert exact_sum([view.keyed_total, view.unkeyed_total]) == view.billed_total
    for line in view.lines:
        assert parse_money(line.value) == Decimal(line.amount)
