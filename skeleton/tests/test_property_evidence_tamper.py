"""P7: changing any byte of an evidence row fails verification (Req 6.3)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hostile import RUN_TIME, controls, ledger_snapshots
from hypothesis import assume, given
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.evidence import verify_evidence_pack, write_evidence_pack
from nightaudit.matcher import match
from nightaudit.models import LedgerSnapshot


@pytest.mark.property
@given(snapshots=ledger_snapshots(), control=controls(), data=st.data())
def test_property_flipping_any_byte_of_any_evidence_row_fails_verification(
    snapshots: list[LedgerSnapshot], control: ControlConfig, data: st.DataObject
) -> None:
    """P7 (Req 6.3): "For any evidence pack that passes verification, modifying any single byte of any row in
    ``evidence.jsonl`` causes ``verify`` to report a failure."

    A row's bytes include its line ending, so a flipped newline counts too.
    """
    result = match(snapshots, control, RUN_TIME)
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp)
        write_evidence_pack(result, pack)
        assert verify_evidence_pack(pack).ok

        path = pack / "evidence.jsonl"
        lines = path.read_bytes().splitlines(keepends=True)
        assume(lines)  # a pack with no rows has no byte to change
        row = data.draw(st.integers(0, len(lines) - 1), label="row")
        position = data.draw(st.integers(0, len(lines[row]) - 1), label="byte")
        mask = data.draw(st.integers(1, 255), label="xor mask")
        tampered = bytearray(lines[row])
        tampered[position] ^= mask
        lines[row] = bytes(tampered)
        path.write_bytes(b"".join(lines))

        outcome = verify_evidence_pack(pack)
        assert not outcome.ok, f"row {row} byte {position} ^ {mask:#04x} still verified: {outcome.detail}"
