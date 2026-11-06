"""P1: every key lands in exactly one region (Req 3.1)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import pytest
from hostile import CLOUD, RUN_TIME, controls, expected_pending, ledger_snapshots, membership, region_code, snapshot
from hypothesis import given
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record


@pytest.mark.property
@given(snapshots=ledger_snapshots(), control=controls())
def test_property_every_key_lands_in_exactly_one_region_named_by_its_ledgers(
    snapshots: list[LedgerSnapshot], control: ControlConfig
) -> None:
    """P1 (Req 3.1): "For any three ledger snapshots and any control config, every key that appears in at least one
    ledger after normalisation is assigned to exactly one region, and that region is the set of ledger initials that
    contain the key joined in I-O-B order. No key is assigned to more than one region and no key is lost."

    Keys held back by the grace window (Req 4.1) are accounted for in ``pending_keys`` instead of a region.
    """
    result = match(snapshots, control, RUN_TIME)
    present = membership(snapshots, control)
    pending = expected_pending(snapshots, control, RUN_TIME)

    # No key lost, none counted twice: regions and pending split the keys exactly.
    assert set(result.regions) | set(result.pending_keys) == set(present)
    assert not set(result.regions) & set(result.pending_keys)
    assert len(result.pending_keys) == len(set(result.pending_keys))
    assert set(result.pending_keys) == pending

    # The region is the I-O-B join of the ledgers that contain the key.
    for key, code in result.regions.items():
        assert code == region_code(present[key]), key
    for key in result.pending_keys:
        assert LedgerName.observed in present[key] and LedgerName.billed not in present[key], key

    # Findings and summaries count each key once, in the region the partition gave it.
    finding_keys = Counter(f.key for f in result.findings)
    assert all(n == 1 for n in finding_keys.values())
    assert set(finding_keys) == {k for k, c in result.regions.items() if c != "IOB"}
    assert all(f.region_code == result.regions[f.key] for f in result.findings)
    assert {c: s.key_count for c, s in result.region_summaries.items()} == Counter(result.regions.values())


def test_regression_a_naive_and_an_aware_timestamp_on_one_key_are_compared_as_utc() -> None:
    """Shrunk from P1: ``max()`` over a naive and an aware timestamp raised ``TypeError`` and the run crashed.

    A naive timestamp is read as UTC, the rule the built-in connectors already apply.
    """
    observed = [
        Record(ledger=LedgerName.observed, source="inventory-us-east-1", row_id="1", raw_key="i-0aa1", timestamp=ts)
        for ts in (None, datetime(2026, 11, 6, 2, 0), datetime(2026, 11, 6, 2, 0, tzinfo=UTC))
    ]
    result = match([snapshot(LedgerName.intended, []), snapshot(LedgerName.observed, observed),
                    snapshot(LedgerName.billed, [])], CLOUD, RUN_TIME)
    assert result.pending_keys == ["i-0aa1"]
    assert result.regions == {}
    assert result.findings == []
