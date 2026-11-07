"""P14: the morning report escapes every ledger value (ui-kit Req 7.3, 11.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from html.parser import HTMLParser

import pytest
from hostile import RUN_TIME
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record
from nightaudit.report import report_html

#: The only tags report.py writes.
REPORT_TAGS = {
    "html",
    "head",
    "meta",
    "title",
    "style",
    "body",
    "header",
    "p",
    "span",
    "h1",
    "h2",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "dl",
    "div",
    "dt",
    "dd",
    "footer",
}

PAYLOADS = st.sampled_from(
    [
        "<script>alert(1)</script>",
        '"><img src=x onerror=alert(1)>',
        "</td></tr></table><script>alert(1)</script>",
        "<style>body{display:none}</style>",
        "&lt;script&gt;",
        "javascript:alert(1)",
        "'; onmouseover='alert(1)",
        "<!--",
        "]]><svg onload=alert(1)>",
        "\u202eevil\u202c",
    ]
)


class _Collect(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: set[str] = set()
        self.attr_names: set[str] = set()
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        self.attr_names.update(name for name, _ in attrs)

    def handle_data(self, data: str) -> None:
        self.text.append(data)


@pytest.mark.property
@given(st.lists(st.one_of(PAYLOADS, st.text(min_size=1, max_size=40)), min_size=1, max_size=4), PAYLOADS)
def test_property_report_shows_ledger_values_only_as_text(keys: list[str], name: str) -> None:
    observed = [
        Record(
            ledger=LedgerName.observed,
            source="inventory",
            row_id=f"o{i}",
            raw_key=key,
            timestamp=datetime(2026, 9, 1, tzinfo=UTC),
        )
        for i, key in enumerate(keys)
    ]
    billed = [Record(ledger=LedgerName.billed, source="cur", row_id="b0", raw_key=keys[0], amount=None)]
    snapshots = [
        LedgerSnapshot(name=LedgerName.intended, source="i"),
        LedgerSnapshot(name=LedgerName.observed, source="o", records=observed),
        LedgerSnapshot(name=LedgerName.billed, source="b", records=billed),
    ]
    result = match(snapshots, ControlConfig(), RUN_TIME)  # no normalisers: each key is exactly the planted text
    result.control_title = name
    for finding in result.findings:
        finding.name = name
    collected = _Collect()
    collected.feed(report_html(result))
    collected.close()

    assert collected.tags <= REPORT_TAGS
    assert not any(attr.startswith("on") for attr in collected.attr_names)
    text = "".join(collected.text)
    for finding in result.findings:
        assert finding.key in text
    assert name in text
