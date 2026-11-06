"""Headline, money lines and the morning report (ui-kit Req 2, 3, 7): deterministic, with their boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from html.parser import HTMLParser

import pytest
from hostile import CLOUD, RUN_TIME, display_numbers
from nightaudit.matcher import match
from nightaudit.models import HeadlineUi, LedgerName, LedgerSnapshot, LedgerUi, NounUi, Record, RunResult, UiConfig
from nightaudit.report import (
    CALM_HEADLINE,
    headline,
    ledger_key_counts,
    money_text,
    report_csp,
    report_html,
    run_numbers,
    run_view,
)

I, O, B = LedgerName.intended, LedgerName.observed, LedgerName.billed  # noqa: E741 - the ledger initials
OLD = datetime(2026, 9, 1, tzinfo=UTC)

VAMPIRES = UiConfig(
    title="Vampires",
    noun=NounUi(singular="resource", plural="resources"),
    ledgers={
        "intended": LedgerUi(label="Declared", source="Stacks."),
        "observed": LedgerUi(label="Running", source="Inventory."),
        "billed": LedgerUi(label="Billed", source="CUR."),
    },
    headlines={
        "OB": HeadlineUi(one="{count} Vampire is running and on the bill with no approval: {amount} so far.",
                         other="{count} Vampires are running and on the bill with no approval: {amount} so far."),
        "O": HeadlineUi(one="{count} Poltergeist costs nothing.", other="{count} Poltergeists cost nothing."),
        "I": HeadlineUi(one="{count} declared {noun} is gone.", other="{count} declared {noun} are gone."),
    },
)


def rec(ledger: LedgerName, row: str, key: str, amount: str | None = None) -> Record:
    return Record(ledger=ledger, source=ledger.value, row_id=row, raw_key=key,
                  amount=None if amount is None else Decimal(amount), timestamp=OLD if ledger == O else None)


def run_of(*records: Record, ui: UiConfig | None = None, missing: tuple[LedgerName, ...] = ()) -> RunResult:
    snapshots = [
        LedgerSnapshot(name=name, source=name.value, records=[r for r in records if r.ledger == name],
                       missing=name in missing)
        for name in (I, O, B)
    ]
    result = match(snapshots, CLOUD, RUN_TIME)
    if ui is not None:
        result.ui = ui
    return result


def matched(key: str, amount: str = "1.00") -> list[Record]:
    return [rec(I, f"i-{key}", key), rec(O, f"o-{key}", key), rec(B, f"b-{key}", key, amount)]


# --- money_text -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("0", "$0.00"),
        ("-0", "$0.00"),
        ("0E-12", "$0.00"),
        ("1E+5", "$100,000.00"),
        ("0.5", "$0.50"),
        ("41.200", "$41.20"),
        ("0.000000001", "$0.000000001"),
        ("0.123456789", "$0.123456789"),
        ("-3.10", "\u2212$3.10"),
        ("1234567.891", "$1,234,567.891"),
        ("-0.0000000001", "\u2212$0.0000000001"),
    ],
)
def test_money_is_shown_exactly(value: str, text: str) -> None:
    assert money_text(Decimal(value)) == text


def test_money_text_refuses_non_finite_amounts() -> None:
    with pytest.raises(ValueError):
        money_text(Decimal("NaN"))


# --- headline ---------------------------------------------------------------------------------------------------------


def test_zero_findings_reads_as_a_calm_finished_night() -> None:
    result = run_of(*matched("a"), *matched("b"), ui=VAMPIRES)
    assert headline(result) == CALM_HEADLINE == "All three ledgers agree. Nothing to report tonight."
    assert run_view(result).calm


def test_informational_familiars_alone_are_still_a_calm_night() -> None:
    result = run_of(*matched("a"), rec(I, "i2", "fam"), rec(O, "o2", "fam"))
    assert result.region_summaries["IO"].key_count == 1
    assert headline(result) == CALM_HEADLINE
    assert "Familiar" not in headline(result)


def test_one_finding_uses_the_singular_noun_and_verb() -> None:
    result = run_of(*matched("a"), rec(I, "i2", "gone"), ui=VAMPIRES)
    assert headline(result) == "1 declared resource is gone."


def test_two_findings_use_the_plural() -> None:
    result = run_of(rec(I, "i1", "gone-1"), rec(I, "i2", "gone-2"), ui=VAMPIRES)
    assert headline(result) == "2 declared resources are gone."


def test_the_requirement_example_reads_as_written() -> None:
    result = run_of(
        *matched("a"),
        rec(O, "o1", "v1"), rec(B, "b1", "v1", "0.20"),
        rec(O, "o2", "v2"), rec(B, "b2", "v2", "0.19"),
        rec(O, "o3", "v3"), rec(B, "b3", "v3", "0.20"),
        rec(O, "o4", "p1"), rec(O, "o5", "p2"),
        rec(I, "i9", "gone"),
        ui=VAMPIRES,
    )
    assert headline(result) == (
        "3 Vampires are running and on the bill with no approval: $0.59 so far. "
        "2 Poltergeists cost nothing. 1 declared resource is gone."
    )


def test_default_words_name_every_region_in_a_fixed_order() -> None:
    result = run_of(rec(O, "o1", "pg"), rec(I, "i1", "sk"), rec(I, "i2", "wr"), rec(B, "b2", "wr", "2.00"),
                    rec(B, "b3", "ph", "3.00"), rec(O, "o4", "vm"), rec(B, "b4", "vm", "4.00"))
    text = headline(result)
    positions = [text.index(name) for name in ("Vampire", "Phantom", "Wraith", "Poltergeist", "Skeleton")]
    assert positions == sorted(positions)
    assert text.startswith("1 Vampire exists and is on the bill with no approval: $4.00.")


def test_regions_with_no_findings_are_left_out() -> None:
    result = run_of(*matched("a"), rec(O, "o1", "pg"), ui=VAMPIRES)
    assert headline(result) == "1 Poltergeist costs nothing."


def test_a_missing_ledger_is_named_and_no_number_is_claimed() -> None:
    result = run_of(*matched("a"), ui=VAMPIRES, missing=(B,))
    assert headline(result) == "The Billed ledger could not be read, so tonight has no findings."
    assert display_numbers(headline(result)) == set()
    assert not run_view(result).calm
    assert run_view(result).lines == []


def test_two_missing_ledgers_are_both_named() -> None:
    result = run_of(*matched("a"), ui=VAMPIRES, missing=(I, B))
    assert headline(result) == "The Declared and Billed ledgers could not be read, so tonight has no findings."


def test_amounts_with_many_decimals_are_not_rounded_in_the_headline() -> None:
    result = run_of(rec(O, "o1", "v"), rec(B, "b1", "v", "0.000000001"), rec(B, "b2", "v", "0.1"), ui=VAMPIRES)
    assert headline(result) == "1 Vampire is running and on the bill with no approval: $0.100000001 so far."
    assert display_numbers(headline(result)) <= run_numbers(result)


# --- money lines ------------------------------------------------------------------------------------------------------


def test_a_negative_unkeyed_total_is_kept_apart_and_explained() -> None:
    result = run_of(*matched("a", "5.00"), rec(B, "credit", "", "-7.25"), ui=VAMPIRES)
    view = run_view(result)
    assert view.keyed_total == Decimal("5.00")
    assert view.unkeyed_total == Decimal("-7.25")
    assert view.billed_total == Decimal("-2.25")
    assert view.keyed_total + view.unkeyed_total == view.billed_total
    labels = [(line.label, line.value) for line in view.lines]
    assert labels == [
        ("On the bill for 1 resource", "$5.00"),
        ("1 line with no resource id", "\u2212$7.25"),
        ("Billed total", "\u2212$2.25"),
    ]
    assert "credit" in view.lines[1].note.lower()
    assert "7.25" not in headline(result)


def test_a_positive_unkeyed_total_says_what_it_is() -> None:
    result = run_of(*matched("a", "5.00"), rec(B, "tax", "", "0.41"), rec(B, "support", "  ", "1.00"))
    view = run_view(result)
    assert view.lines[1].label == "2 lines with no resource id"
    assert view.lines[1].value == "$1.41"
    assert "Tax" in view.lines[1].note


def test_no_unkeyed_lines_means_no_unkeyed_line() -> None:
    view = run_view(run_of(*matched("a", "5.00")))
    assert [line.label for line in view.lines] == ["On the bill for 1 item", "Billed total"]


# --- key counts -------------------------------------------------------------------------------------------------------


def test_ledgers_count_keys_not_rows() -> None:
    result = run_of(*matched("a"), rec(B, "b-dup", "a", "1.00"), rec(B, "tax", "", "0.10"), rec(O, "o2", "x"))
    assert ledger_key_counts(result) == {"intended": 1, "observed": 2, "billed": 1}


def test_an_incomplete_run_counts_no_keys() -> None:
    result = run_of(*matched("a"), missing=(O,))
    assert ledger_key_counts(result) == {"intended": None, "observed": None, "billed": None}


# --- report -----------------------------------------------------------------------------------------------------------


class _Collect(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str | None]] = []
        self.text: list[str] = []
        self.cells: list[tuple[str, str]] = []
        self._cell: str | None = None
        self._class = ""
        self.headline = ""
        self._in_headline = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.extend(attrs)
        cls = dict(attrs).get("class") or ""
        if tag == "td":
            self._cell, self._class = "", cls
        if tag == "p" and cls == "headline":
            self._in_headline = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell is not None:
            self.cells.append((self._class, self._cell))
            self._cell = None
        if tag == "p":
            self._in_headline = False

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._cell is not None:
            self._cell += data
        if self._in_headline:
            self.headline += data


def parse(page: str) -> _Collect:
    collected = _Collect()
    collected.feed(page)
    collected.close()
    return collected


PAYLOAD = '<script>alert("x")</script><img src=x onerror=alert(1)>'


def test_the_report_is_self_contained() -> None:
    page = report_html(run_of(*matched("a"), rec(O, "o1", "pg")))
    lowered = page.lower()
    for forbidden in ("http:", "https:", "src=", "<script", "<link", "url(", "@import"):
        assert forbidden not in lowered


def test_a_planted_script_appears_only_as_text() -> None:
    result = run_of(*matched("a"), Record(ledger=O, source="o", row_id="o1", raw_key=PAYLOAD, timestamp=OLD))
    result.control_title = PAYLOAD
    page = report_html(result)
    collected = parse(page)
    assert "script" not in collected.tags and "img" not in collected.tags
    assert not any(name.startswith("on") for name, _ in collected.attrs)
    assert PAYLOAD.lower() in "".join(collected.text)


def test_every_number_in_the_report_headline_and_table_is_in_the_run() -> None:
    result = run_of(
        *matched("a"), rec(O, "o1", "v1"), rec(B, "b1", "v1", "41.20"), rec(I, "i2", "gone"),
        rec(B, "tax", "", "-1.5"), ui=VAMPIRES,
    )
    collected = parse(report_html(result))
    numbers = run_numbers(result)
    assert display_numbers(collected.headline) <= numbers
    for cls, cell in collected.cells:
        if cls != "key":
            assert display_numbers(cell) <= numbers, cell


def test_the_report_lists_new_findings_first_and_says_since_when() -> None:
    result = run_of(rec(O, "o1", "pg"), rec(I, "i1", "sk"))
    result.findings[0].status = "persisting"
    result.findings[0].first_seen = datetime(2026, 11, 2, 2, tzinfo=UTC)
    result.findings[0].nights_persisted = 4
    old_key = result.findings[0].key
    cells = [cell for cls, cell in parse(report_html(result)).cells if cls == "key"]
    assert cells[-1] == old_key
    assert "02 Nov 2026" in report_html(result)


def test_the_report_marks_a_recorded_run_in_words() -> None:
    assert "synthetic account" in report_html(run_of(*matched("a")), recorded=True)
    assert "synthetic account" not in report_html(run_of(*matched("a")))


def test_the_report_policy_allows_only_its_own_style() -> None:
    policy = report_csp()
    assert policy.startswith("default-src 'none'; style-src 'sha256-")
    assert "script-src" not in policy


def test_the_headline_splits_into_a_lead_and_one_sentence_per_region() -> None:
    result = run_of(*matched("a"), rec(O, "o1", "v1"), rec(B, "b1", "v1", "0.20"), rec(O, "o4", "p1"), ui=VAMPIRES)
    sentences = run_view(result).headline_sentences
    assert sentences == [
        "1 Vampire is running and on the bill with no approval: $0.20 so far.",
        "1 Poltergeist costs nothing.",
    ]
    assert " ".join(sentences) == headline(result)
    assert run_view(run_of(*matched("a"))).headline_sentences == [CALM_HEADLINE]
