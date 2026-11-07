"""P8: a model response citing a number outside the evidence is replaced by the template (Req 7.2)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from hostile import CLOUD, LEDGERS, RUN_TIME, amounts, exact_sum, numbers_in, raw_keys, records
from hypothesis import assume, given
from hypothesis import strategies as st
from nightaudit.control import RegionOverride, resolve_region
from nightaudit.explain import ModelConfig, explain_finding, resolve_template
from nightaudit.models import FINDING_REGIONS, INFORMATIONAL_REGIONS, Finding, LedgerName, Record


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts is not None else None


def _iso_text() -> st.SearchStrategy[str]:
    return st.builds(lambda seconds: (RUN_TIME + timedelta(seconds=seconds)).isoformat(), st.integers(-10**8, 10**6))


def evidence_numbers(finding: Finding) -> set[Decimal]:
    """Every number written in the finding's evidence rows and in its decided fields (audit rule 2)."""
    nums: set[Decimal] = {finding.billed_amount, *map(Decimal, finding.duplicate_counts.values())}
    if finding.nights_persisted is not None:
        nums.add(Decimal(finding.nights_persisted))
    texts = [finding.key, _iso(finding.first_seen), *finding.context.values()]
    for r in finding.records:
        if r.amount is not None:
            nums.add(r.amount)
        texts += [r.row_id, r.raw_key, r.key, _iso(r.timestamp), *r.attrs.values()]
    for text in texts:
        nums |= numbers_in(text)
    return nums


@st.composite
def findings(draw: st.DrawFn) -> Finding:
    key = draw(raw_keys().filter(bool))
    recs = [
        r.model_copy(update={"key": key})
        for r in draw(st.lists(st.sampled_from(LEDGERS).flatmap(records), min_size=1, max_size=5))
    ]
    code = draw(st.sampled_from(sorted(FINDING_REGIONS | INFORMATIONAL_REGIONS)))
    name, severity, meaning = resolve_region(code, CLOUD)
    counts = {ledger.value: n for ledger in LEDGERS if (n := sum(r.ledger == ledger for r in recs)) > 1}
    return Finding(
        key=key,
        region_code=code,
        name=name,
        severity=severity,
        meaning=meaning,
        informational=code in INFORMATIONAL_REGIONS,
        records=recs,
        billed_amount=exact_sum(r.amount for r in recs if r.ledger == LedgerName.billed and r.amount is not None),
        duplicate_counts=counts,
        nights_persisted=draw(st.one_of(st.none(), st.integers(0, 400))),
        first_seen=draw(st.one_of(st.none(), st.just(RUN_TIME))),
        context=draw(st.fixed_dictionaries({}, optional={
            "created_by": st.text(max_size=24),
            "created_at": st.one_of(_iso_text(), st.text(max_size=24), st.from_regex(r"\A\d{8,14}\Z")),
            "event_id": st.text(max_size=24),
        })),
    )


def _render(number: Decimal, draw: st.DrawFn) -> str:
    text = format(number, "f")
    if number < 0 and draw(st.booleans()):
        text = "\u2212" + text[1:]  # typographic minus
    return draw(st.sampled_from(["", "$", "USD "])) + text


@st.composite
def poisoned(draw: st.DrawFn) -> tuple[Finding, str, Decimal]:
    """A finding and a fluent response that cites evidence numbers plus one number that is not in the evidence."""
    finding = draw(findings())
    evidence = evidence_numbers(finding)
    near = sorted(evidence)
    derived = st.sampled_from(near).flatmap(lambda e: st.sampled_from(
        [-e, e * 10, e + 1, e - Decimal("0.01"), e.scaleb(-1)])) if near else st.nothing()
    stray = draw(st.one_of(amounts(), st.integers(-10**6, 10**9).map(Decimal), derived))
    assume(stray not in evidence)
    cited = [_render(e, draw) for e in draw(st.lists(st.sampled_from(near), max_size=3))] if near else []
    words = st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8)
    parts = cited + [_render(stray, draw)] + draw(st.lists(words, max_size=6))
    response = " ".join(draw(st.permutations(parts))) + "."
    return finding, response, stray


@pytest.mark.property
@given(case=poisoned())
def test_property_a_response_citing_a_number_outside_the_evidence_is_replaced_by_the_template(
    case: tuple[Finding, str, Decimal],
) -> None:
    """P8 (Req 7.2): "For any model response text that contains a number not present in the finding's evidence, the
    explanation guard discards the response and returns the deterministic template."

    The rejection must be recorded, and the template that replaces it must itself cite only evidence numbers
    (audit rule 2, tech rule "the output must still pass the explanation guard").
    """
    finding, response, stray = case
    prompts: list[str] = []

    def fake_model(prompt: str) -> str:
        prompts.append(prompt)
        return response

    explanation = explain_finding(finding, ModelConfig(enabled=True, model_id="fake"), CLOUD, model_call=fake_model)

    assert len(prompts) == 1
    assert explanation.source == "template", f"{stray} accepted in {response!r}"
    assert explanation.rejected
    assert explanation.rejection_reason
    assert explanation.text == resolve_template(finding, CLOUD)
    assert numbers_in(explanation.text) <= evidence_numbers(finding), explanation.text


def _phantom(records: list[Record], context: dict[str, str] | None = None) -> Finding:
    name, severity, meaning = resolve_region("B", CLOUD)
    return Finding(
        key="i-0aa1", region_code="B", name=name, severity=severity, meaning=meaning, informational=False,
        records=records, context=context or {},
        billed_amount=exact_sum(r.amount for r in records if r.ledger == LedgerName.billed and r.amount is not None),
    )


def _row(ledger: LedgerName, **fields: object) -> Record:
    return Record.model_validate({"ledger": ledger, "source": "src", "row_id": "1", "raw_key": "i-0aa1",
                                  "key": "i-0aa1", **fields})


def test_regression_a_response_that_negates_an_evidence_number_is_rejected() -> None:
    """Shrunk from P8: evidence held ``41.20`` (an attribute value) and the response ``"-41.20."`` was accepted,
    because the guard read numbers without their sign.
    """
    finding = _phantom([_row(LedgerName.intended, attrs={"project": "41.20"})])
    explanation = explain_finding(finding, ModelConfig(enabled=True, model_id="fake"), CLOUD,
                                  model_call=lambda prompt: "-41.20.")
    assert explanation.source == "template"
    assert explanation.rejected
    assert "-41.20" in str(explanation.rejection_reason)


def test_regression_the_template_writes_an_amount_without_an_exponent() -> None:
    """Shrunk from P8: a billed ``Decimal("1E-7")`` was written as ``$1E-7``, citing ``7``, which is not evidence."""
    finding = _phantom([_row(LedgerName.billed, amount=Decimal("1E-7"))])
    text = resolve_template(finding, CLOUD)
    assert "$0.0000001." in text
    assert numbers_in(text) <= evidence_numbers(finding)


def test_regression_the_template_cites_a_creation_date_only_when_it_starts_with_an_iso_date() -> None:
    """Shrunk from P8: ``created_at="000000000२0"`` was cut to its first ten characters, citing ``000000000२`` (2)."""
    hostile = _phantom([_row(LedgerName.billed)], {"created_by": "0", "created_at": "000000000\u0968" + "0"})
    assert "Created on" not in resolve_template(hostile, CLOUD)
    dated = _phantom([_row(LedgerName.billed)], {"created_by": "ci-role", "created_at": "2026-11-04T02:00:00Z"})
    assert "Created on 2026-11-04 by ci-role." in resolve_template(dated, CLOUD)


def test_the_default_template_starts_with_the_meaning_and_not_the_key() -> None:
    """The UI shows the key beside the explanation, so the default wording opens with the meaning."""
    finding = _phantom([_row(LedgerName.billed, amount=Decimal("41.20"))])
    text = resolve_template(finding, CLOUD)
    assert text.startswith(finding.meaning)
    assert not text.startswith(finding.key)
    assert f"{finding.key}:" not in text
    assert "On the bill: $41.20." in text


def test_a_custom_template_can_still_write_the_key() -> None:
    finding = _phantom([_row(LedgerName.billed, amount=Decimal("41.20"))])
    control = CLOUD.model_copy(update={"regions": {"B": RegionOverride(template="{key} costs {billed_amount}.")}})
    assert resolve_template(finding, control) == "i-0aa1 costs 41.20."


def test_the_number_guard_still_rejects_a_stray_number_when_the_template_has_no_key() -> None:
    finding = _phantom([_row(LedgerName.billed, amount=Decimal("41.20"))])
    explanation = explain_finding(finding, ModelConfig(enabled=True, model_id="fake"), CLOUD,
                                  model_call=lambda prompt: "It costs 99.99 a night.")
    assert explanation.source == "template"
    assert explanation.rejected
    assert explanation.text.startswith(finding.meaning)
    assert numbers_in(explanation.text) <= evidence_numbers(finding)
