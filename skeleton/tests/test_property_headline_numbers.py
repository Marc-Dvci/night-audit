"""P11: every number in the headline and the morning report comes from the run (ui-kit Req 2.2, 2.3, 7.4)."""

from __future__ import annotations

from html.parser import HTMLParser

import pytest
from hostile import RUN_TIME, controls, display_numbers, ledger_snapshots
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import FINDING_REGIONS, HeadlineUi, LedgerName, LedgerSnapshot, NounUi, RunResult, UiConfig
from nightaudit.report import CALM_HEADLINE, headline, headline_numbers, report_html, run_numbers

WORDED = UiConfig(
    noun=NounUi(singular="resource", plural="resources"),
    headlines={
        code: HeadlineUi(
            one=f"ONE {code} {{count}} {{noun}} {{amount}}.", other=f"MANY {code} {{count}} {{noun}} {{amount}}."
        )
        for code in FINDING_REGIONS
    },
)


class _Cells(HTMLParser):
    """Collects the headline paragraph and every table cell that is not a ledger key."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.texts: list[tuple[str, str]] = []
        self._open: str | None = None
        self._kind = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        cls = dict(attrs).get("class") or ""
        if (tag == "td" and cls != "key") or (tag == "p" and cls == "headline"):
            self._open = ""
            self._kind = "headline" if tag == "p" else "cell"

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "p") and self._open is not None:
            self.texts.append((self._kind, self._open))
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self._open += data


def _run(
    snapshots: list[LedgerSnapshot], control: ControlConfig, worded: bool, missing: LedgerName | None
) -> RunResult:
    if missing is not None:
        snapshots = [s.model_copy(update={"missing": True}) if s.name == missing else s for s in snapshots]
    result = match(snapshots, control, RUN_TIME)
    if worded:
        result.ui = WORDED
    return result


@pytest.mark.property
@given(ledger_snapshots(), controls(), st.booleans(), st.one_of(st.none(), st.sampled_from(list(LedgerName))))
def test_property_headline_numbers_come_from_the_run(
    snapshots: list[LedgerSnapshot], control: ControlConfig, worded: bool, missing: LedgerName | None
) -> None:
    result = _run(snapshots, control, worded, missing)
    text = headline(result)
    assert display_numbers(text) <= headline_numbers(result)

    findings = [f for f in result.findings if not f.informational]
    if result.complete and not findings:
        assert text == CALM_HEADLINE
    if worded and result.complete:
        for code in FINDING_REGIONS:
            count = result.region_summaries[code].key_count if code in result.region_summaries else 0
            assert (f"ONE {code} " in text) == (count == 1)
            assert (f"MANY {code} " in text) == (count > 1)
            if count == 1:
                assert f"ONE {code} 1 resource " in text


@pytest.mark.property
@given(ledger_snapshots(), controls(), st.booleans(), st.one_of(st.none(), st.sampled_from(list(LedgerName))))
def test_property_report_numbers_come_from_the_run(
    snapshots: list[LedgerSnapshot], control: ControlConfig, worded: bool, missing: LedgerName | None
) -> None:
    result = _run(snapshots, control, worded, missing)
    cells = _Cells()
    cells.feed(report_html(result))
    numbers, headline_ok = run_numbers(result), headline_numbers(result)
    for kind, text in cells.texts:
        # Only the headline may round, and only its amounts; every table cell shows the exact value.
        assert display_numbers(text) <= (headline_ok if kind == "headline" else numbers), text
