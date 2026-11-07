"""Differential test (night shift Req 3.2): the Python matcher and the Lean model's executable agree on every region.

The Lean model (``lean/NightAudit/Region.lean``) is the function the partition theorems are about. Its executable,
``lean/.lake/build/bin/regions``, reads JSON Lines and prints a region code or ``none`` for each line.

For each generated night the Python matcher gets raw records with hostile keys. The Lean executable gets the same
records' keys after the control's normaliser chain, per ledger, in record order, repeats kept and empty keys left out
(the matcher reports those as unkeyed). Both are asked for the region of every key in the union and of hostile keys
that are probably outside it, normalised with each ledger's chain, and of the empty key.

The model has no grace window and no scope filter, so the records here carry no timestamp and the control no scope.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from hostile import LEDGERS, RUN_TIME, controls, key_of, ledger_snapshots, raw_keys
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerSnapshot
from nightaudit.normalisers import normalise

LEAN_DIR = Path(__file__).resolve().parents[2] / "lean"
LAKE = shutil.which("lake")
EXE = LEAN_DIR / ".lake" / "build" / "bin" / ("regions.exe" if os.name == "nt" else "regions")
#: Set in CI's lean job, where a missing toolchain is a failure, not a skip.
REQUIRED = os.environ.get("NIGHTAUDIT_REQUIRE_LEAN") == "1"

pytestmark = [
    pytest.mark.lean,
    pytest.mark.skipif(
        LAKE is None and not REQUIRED, reason="lake is not on the path, so the Lean model's executable cannot be built"
    ),
    pytest.mark.timeout(1200),
]

Night = tuple[list[LedgerSnapshot], ControlConfig, list[str]]


@pytest.fixture(scope="module")
def regions_exe() -> Path:
    """Build the executable once (nothing to do when CI has built it) and return its path."""
    assert LAKE is not None, "NIGHTAUDIT_REQUIRE_LEAN is set but lake is not on the path"
    built = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [LAKE, "build", "regions"], cwd=LEAN_DIR, capture_output=True, text=True, timeout=1200, check=False
    )
    if built.returncode != 0:
        pytest.fail(f"lake build regions failed:\n{built.stdout}\n{built.stderr}")
    assert EXE.is_file(), f"lake build did not produce {EXE}"
    return EXE


def run_exe(exe: Path, lines: bytes) -> tuple[int, list[str]]:
    """Run the executable on *lines*; its output split on newlines only (``splitlines`` would also split on U+0085)."""
    done = subprocess.run([str(exe)], input=lines, capture_output=True, timeout=60, check=False)  # noqa: S603
    text = done.stdout.decode("utf-8").replace("\r\n", "\n")
    return done.returncode, text.removesuffix("\n").split("\n") if text else []


def lean_regions(exe: Path, ledgers: dict[str, list[str]], keys: list[str]) -> list[str]:
    """The executable's answer for each key, in order. Bytes, so no newline translation on Windows."""
    data = "".join(json.dumps({**ledgers, "key": key}, ensure_ascii=False) + "\n" for key in keys)
    code, out = run_exe(exe, data.encode("utf-8"))
    assert code == 0 and len(out) == len(keys), out
    return out


def lean_ledgers(snapshots: list[LedgerSnapshot], control: ControlConfig) -> dict[str, list[str]]:
    """Each ledger as the Lean model takes it: its records' normalised keys in order, empty keys left out."""
    ledgers: dict[str, list[str]] = {}
    for snapshot in snapshots:
        keys = (key_of(record, control) for record in snapshot.records)
        ledgers[snapshot.name.value] = [key for key in keys if key != ""]
    return ledgers


@st.composite
def nights(draw: st.DrawFn) -> Night:
    """Hostile ledgers without timestamps, any control without a scope, and raw keys to ask about as well."""
    control = draw(controls()).model_copy(update={"scope": None})
    snapshots = [
        s.model_copy(update={"records": [r.model_copy(update={"timestamp": None}) for r in s.records]})
        for s in draw(ledger_snapshots())
    ]
    return snapshots, control, draw(st.lists(raw_keys(), max_size=4))


@pytest.mark.property
@settings(
    max_examples=500, derandomize=True, database=None, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
@given(night=nights())
def test_property_the_lean_model_and_the_python_matcher_give_every_key_the_same_region(
    regions_exe: Path, night: Night
) -> None:
    """Req 3.2: on the same inputs, `regionOf` in Lean and `match` in Python give identical regions."""
    snapshots, control, raw_extra = night
    result = match(snapshots, control, RUN_TIME)
    assert result.complete and result.pending_keys == [], "the model has no grace window"

    ledgers = lean_ledgers(snapshots, control)
    union = sorted({key for keys in ledgers.values() for key in keys})
    ctx = {"alias_domains": control.alias_domains}
    outside = [
        normalise(raw, control.normalisers.get(ledger.value, []), ctx) for raw in raw_extra for ledger in LEDGERS
    ]
    asked = list(dict.fromkeys([*union, *outside, ""]))

    lean = dict(zip(asked, lean_regions(regions_exe, ledgers, asked), strict=True))
    python = {key: result.regions.get(key, "none") for key in asked}
    assert lean == python
    assert set(result.regions) == set(union), "the keys with a region are exactly the union"


def test_the_lean_executable_names_each_of_the_seven_regions_and_none(regions_exe: Path) -> None:
    """A fixed table, so a disagreement in the property test can be read against known answers."""
    ledgers = {
        "intended": ["i", "io", "ib", "iob", "i"],
        "observed": ["o", "io", "ob", "iob"],
        "billed": ["b", "ib", "ob", "iob"],
    }
    expected = {
        "i": "I",
        "o": "O",
        "b": "B",
        "io": "IO",
        "ib": "IB",
        "ob": "OB",
        "iob": "IOB",
        "nowhere": "none",
        "": "none",
        "I": "none",
        'i\u2028"x\\': "none",
    }
    assert dict(zip(expected, lean_regions(regions_exe, ledgers, list(expected)), strict=True)) == expected


def test_the_lean_executable_reports_a_malformed_line_and_exits_1(regions_exe: Path) -> None:
    code, out = run_exe(regions_exe, b'{"intended": [], "observed": [], "billed": [], "key": "a"}\n{"intended": [1]}\n')
    assert code == 1 and out[0] == "none" and out[1].startswith("error: ")
