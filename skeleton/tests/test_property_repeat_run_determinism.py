"""P10: identical inputs at the same run time give identical findings and evidence (Req 5.3)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hostile import RUN_TIME, controls, ledger_snapshots
from hypothesis import given
from nightaudit.control import ControlConfig
from nightaudit.evidence import write_evidence_pack
from nightaudit.matcher import match
from nightaudit.models import LedgerSnapshot


@pytest.mark.property
@given(snapshots=ledger_snapshots(), control=controls())
def test_property_repeating_a_run_with_identical_inputs_gives_identical_findings_and_evidence_hash(
    snapshots: list[LedgerSnapshot], control: ControlConfig
) -> None:
    """P10 (Req 5.3): "For any control config and set of ledger inputs, running the matcher twice with identical
    inputs at the same run time produces identical findings (same keys, regions, amounts) and an identical evidence
    chain hash."

    The second run gets a deep copy of the inputs, so it cannot reuse objects the first run touched.
    """
    before = [s.model_dump() for s in snapshots]
    first = match(snapshots, control, RUN_TIME)
    second = match([s.model_copy(deep=True) for s in snapshots], control.model_copy(deep=True), RUN_TIME)
    assert [s.model_dump() for s in snapshots] == before  # the matcher does not mutate its inputs

    assert [f.model_dump() for f in first.findings] == [f.model_dump() for f in second.findings]
    assert first.regions == second.regions
    assert first.region_summaries == second.region_summaries
    with tempfile.TemporaryDirectory() as tmp:
        one, two = Path(tmp) / "one", Path(tmp) / "two"
        assert write_evidence_pack(first, one) == write_evidence_pack(second, two)
        assert (one / "evidence.jsonl").read_bytes() == (two / "evidence.jsonl").read_bytes()
