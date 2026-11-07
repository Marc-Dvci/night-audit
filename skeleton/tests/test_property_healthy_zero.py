"""P3: a healthy control produces zero findings (Req 3.3)."""

from __future__ import annotations

import pytest
from hostile import CLOUD, LEDGERS, PEOPLE, RUN_TIME, WHITESPACE, raw_keys, records, snapshot
from hypothesis import assume, given
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record
from nightaudit.normalisers import normalise

#: Characters ``str.strip()`` removes. U+200B is left out: it is not whitespace, so a key padded with it is a
#: different key (like a lookalike), which would break P3's precondition rather than test it.
SPACES = "".join(c for c in WHITESPACE if c.isspace())


def _variant(draw: st.DrawFn, ledger: LedgerName, key: str, control: ControlConfig) -> str:
    """A raw spelling of *key* as another system would write it: case, padding, ARN wrapper, +tag, alias domain."""
    raw = "".join(c.upper() if draw(st.booleans()) else c for c in key) if draw(st.booleans()) else key
    if control is CLOUD and ledger == LedgerName.billed and draw(st.booleans()):
        raw = draw(st.sampled_from(("arn:aws:ec2:us-east-1:111122223333:instance/", "arn:aws:s3:::"))) + raw
    if control is PEOPLE and "@" in raw:
        local, domain = raw.rsplit("@", 1)
        if draw(st.booleans()):
            local = f"{local}+{draw(st.text(max_size=4))}"
        if domain.lower() == "hollowpines.com" and draw(st.booleans()):
            domain = "HollowPines.org"
        raw = f"{local}@{domain}"
    return draw(st.text(SPACES, max_size=2)) + raw + draw(st.text(SPACES, max_size=2))


@st.composite
def healthy_ledgers(draw: st.DrawFn) -> tuple[ControlConfig, list[LedgerSnapshot]]:
    """The same keys in all three ledgers, each spelled 1-3 times per ledger, plus rows that have no key at all.

    Keys start from hostile raw keys reduced by the intended chain, so most cases meet P3's precondition; the
    ``assume`` in the test still rejects any whose spellings do not normalise alike (``"stra\\u00dfe".upper()`` is
    ``"STRASSE"``, an ARN in intended is not reduced by the cloud chain).
    """
    control = draw(st.sampled_from((CLOUD, PEOPLE)))
    ctx = {"alias_domains": control.alias_domains}
    raw = draw(st.lists(raw_keys(), min_size=1, max_size=8))
    keys = sorted({k for r in raw if (k := normalise(r, control.normalisers["intended"], ctx))})
    assume(keys)
    snapshots: list[LedgerSnapshot] = []
    for ledger in LEDGERS:
        recs: list[Record] = []
        for key in keys:
            for _ in range(draw(st.integers(1, 3))):
                recs.append(draw(records(ledger, st.just(_variant(draw, ledger, key, control)))))
        recs += draw(st.lists(records(ledger, st.sampled_from(["", "   ", "\t\n", "arn:aws:s3:::"])), max_size=2))
        snapshots.append(snapshot(ledger, draw(st.permutations(recs))))
    return control, snapshots


@pytest.mark.property
@given(case=healthy_ledgers())
def test_property_same_keys_in_all_three_ledgers_produce_zero_findings(
    case: tuple[ControlConfig, list[LedgerSnapshot]],
) -> None:
    """P3 (Req 3.3): "For any set of records where the intended, observed and billed ledgers contain the same set of
    normalised keys, the matcher produces zero findings."
    """
    control, snapshots = case
    ctx = {"alias_domains": control.alias_domains}
    key_sets = [
        {k for r in s.records if (k := normalise(r.raw_key, control.normalisers[s.name.value], ctx))} for s in snapshots
    ]
    # Precondition of P3: the spellings normalise to the same key set in every ledger.
    assume(key_sets[0] == key_sets[1] == key_sets[2] != set())

    result = match(snapshots, control, RUN_TIME)
    assert result.findings == []
    assert result.pending_keys == []
    assert set(result.regions.values()) == {"IOB"}
