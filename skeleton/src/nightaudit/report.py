"""What a person reads about a run: the headline, the money lines and the morning report (ui-kit Req 2, 3, 7).

Everything here is a pure function of a ``RunResult``. Every number in the output is a value of the run, formatted
without rounding, so the page, the report and the evidence agree (audit rule 2). Ledger values are untrusted and are
escaped wherever they enter HTML (audit rule 4).
"""

from __future__ import annotations

import base64
import decimal
import hashlib
import html
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from .control import DEFAULT_HEADLINES, fill_region_name
from .models import REGION_CODES, Finding, HeadlineUi, LedgerName, RunResult, UnkeyedUi

#: Headline order: the regions on the bill first, then the unbilled ones, as in the Req 2.2 example (OB, O, I).
HEADLINE_ORDER: tuple[str, ...] = ("OB", "B", "IB", "O", "I")
#: Display order of every region (findings, then informational, then matched).
DISPLAY_ORDER: tuple[str, ...] = ("OB", "B", "IB", "I", "O", "IO", "IOB")

CALM_HEADLINE = "All three ledgers agree. Nothing to report tonight."
#: How a recorded demo run is marked, in the report and on the page. It names no domain, so it fits every app.
RECORDED_TEXT = "Recorded run of synthetic data, not live data"
MINUS = "\u2212"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
#: Sums of money never round: the default 28-digit context drops digits (the matcher uses the same rule).
_EXACT = decimal.Context(
    prec=decimal.MAX_PREC,
    Emax=decimal.MAX_EMAX,
    Emin=decimal.MIN_EMIN,
    traps=[decimal.InvalidOperation, decimal.Inexact, decimal.Overflow],
)


# --- Money --------------------------------------------------------------------------------------------------------


def money_text(value: Decimal) -> str:
    """Show an amount exactly: ``$1,234.50``, ``−$3.10``, ``$0.000000001``. Never rounds, never uses a float.

    Zero (including negative zero) is ``$0.00``. The fraction keeps at least two digits and every significant digit
    beyond them. The minus sign is U+2212.
    """
    if not value.is_finite():
        raise ValueError(f"amount {value} is not a finite number")
    if value.is_zero():
        return "$0.00"
    sign = MINUS if value.is_signed() else ""
    whole, _, fraction = format(value.copy_abs(), "f").partition(".")  # copy_abs never rounds; abs() would
    fraction = fraction.rstrip("0").ljust(2, "0")
    return f"{sign}${int(whole):,}.{fraction}"


# --- Counts -------------------------------------------------------------------------------------------------------


def ledger_key_counts(run: RunResult) -> dict[str, int | None]:
    """Distinct keys per ledger (Req 2.4, 2.5). Rows with no key never count. ``None`` when a ledger was not matched."""
    counts: dict[str, int | None] = {name.value: None for name in LedgerName}
    if not run.complete:
        return counts
    for snapshot in run.snapshots:
        if snapshot.missing:
            continue
        counts[snapshot.name.value] = len({r.key for r in snapshot.records if r.key is not None})
    return counts


def _findings(run: RunResult) -> list[Finding]:
    return [f for f in run.findings if not f.informational]


def _template(run: RunResult, code: str) -> HeadlineUi:
    configured = run.ui.headlines.get(code)
    if configured is not None:
        return configured
    # A run saved before the UI kit has no headlines; build the default from the names it recorded.
    name = run.region_names.get(code, code)
    one, other = DEFAULT_HEADLINES[code]
    return HeadlineUi(one=fill_region_name(one, name), other=fill_region_name(other, name))


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def headline_sentences(run: RunResult) -> list[str]:
    """Tonight's result as sentences, computed from the region summaries (Req 2.2, 2.3). The first is the lead."""
    if not run.complete:
        labels = [run.ui.ledgers[n].label if n in run.ui.ledgers else n for n in run.missing_ledgers]
        noun = "ledger" if len(labels) == 1 else "ledgers"
        return [f"The {_join(labels)} {noun} could not be read, so tonight has no findings."]
    if not _findings(run):
        return [CALM_HEADLINE]
    sentences: list[str] = []
    for code in HEADLINE_ORDER:
        summary = run.region_summaries.get(code)
        if summary is None or summary.key_count == 0:
            continue
        template = _template(run, code)
        one = summary.key_count == 1
        sentences.append(
            (template.one if one else template.other).format(
                count=summary.key_count,
                amount=money_text(summary.billed_amount),
                noun=run.ui.noun.singular if one else run.ui.noun.plural,
            )
        )
    return sentences


def headline(run: RunResult) -> str:
    """Tonight's result in one or a few sentences (Req 2.2, 2.3)."""
    return " ".join(headline_sentences(run))


# --- The view the page reads ------------------------------------------------------------------------------------------


class MoneyLine(BaseModel):
    """One printed summary line: a label, an exact amount and an optional sentence explaining it."""

    label: str
    value: str
    amount: str
    note: str = ""


class RunView(BaseModel):
    """Everything the page shows that is derived from the run, computed once in Python."""

    headline: str
    #: The same headline, one sentence per region. The page prints the first large and the rest beneath it.
    headline_sentences: list[str] = Field(default_factory=list)
    calm: bool
    ledger_keys: dict[str, int | None]
    keyed_total: Decimal
    unkeyed_total: Decimal
    billed_total: Decimal
    lines: list[MoneyLine] = Field(default_factory=list)
    finding_count: int
    new_count: int
    persisting_count: int
    pending_count: int
    resolved_count: int


def _unkeyed_billed_rows(run: RunResult) -> int:
    return sum(1 for u in run.unkeyed if u.ledger == LedgerName.billed and u.amount is not None)


def run_view(run: RunResult) -> RunView:
    """The headline, the key counts and the money lines of a run (Req 2, 3)."""
    findings = _findings(run)
    with decimal.localcontext(_EXACT):  # the default 28-digit context would round the sum
        keyed_total = sum((s.billed_amount for s in run.region_summaries.values()), Decimal("0"))
        conserved = keyed_total + run.billed_unkeyed == run.billed_total
    unkeyed_total = run.billed_unkeyed
    if not conserved:
        raise ValueError(f"amounts are not conserved: {keyed_total} + {unkeyed_total} != {run.billed_total}")
    keys = ledger_key_counts(run)
    lines: list[MoneyLine] = []
    if run.complete:
        billed_keys = keys["billed"] or 0
        noun = run.ui.noun.singular if billed_keys == 1 else run.ui.noun.plural
        lines.append(
            MoneyLine(
                label=f"On the bill for {billed_keys} {noun}", value=money_text(keyed_total), amount=str(keyed_total)
            )
        )
        rows = _unkeyed_billed_rows(run)
        if rows:
            words = run.ui.unkeyed
            # The credits sentence describes a cloud bill, so it is only used while the default words are (Req 10.4).
            note = (
                "Negative because credits are larger than tax and support. A credit is expected here."
                if unkeyed_total < 0 and words == UnkeyedUi()
                else words.explanation
            )
            lines.append(
                MoneyLine(
                    label=f"{rows} {words.singular if rows == 1 else words.plural}",
                    value=money_text(unkeyed_total),
                    amount=str(unkeyed_total),
                    note=note,
                )
            )
        lines.append(MoneyLine(label="Billed total", value=money_text(run.billed_total), amount=str(run.billed_total)))
    return RunView(
        headline=headline(run),
        headline_sentences=headline_sentences(run),
        calm=run.complete and not findings,
        ledger_keys=keys,
        keyed_total=keyed_total,
        unkeyed_total=unkeyed_total,
        billed_total=run.billed_total,
        lines=lines,
        finding_count=len(findings),
        new_count=sum(1 for f in findings if f.status == "new"),
        persisting_count=sum(1 for f in findings if f.status == "persisting"),
        pending_count=len(run.pending_keys),
        resolved_count=len([f for f in run.resolved if not f.informational]),
    )


def _date_numbers(dt: datetime | None) -> set[Decimal]:
    if dt is None:
        return set()
    d = dt.astimezone(UTC) if dt.tzinfo is not None else dt
    return {Decimal(d.day), Decimal(d.year)}


def run_numbers(run: RunResult) -> set[Decimal]:
    """Every number a run contains that code may print: counts, amounts, nights and calendar days and years.

    Tests use it as the oracle for "every number comes from the run" (Req 2.2, 7.4). Ledger text (keys, attributes) is
    not in this set: it is printed as text, never as a number.
    """
    view = run_view(run)
    nums: set[Decimal] = {
        Decimal(view.finding_count),
        Decimal(view.new_count),
        Decimal(view.persisting_count),
        Decimal(view.pending_count),
        Decimal(view.resolved_count),
        Decimal(len(run.findings)),
        Decimal(_unkeyed_billed_rows(run)),
        view.keyed_total,
        view.unkeyed_total,
        view.billed_total,
    }
    nums.update(Decimal(n) for n in view.ledger_keys.values() if n is not None)
    for code in REGION_CODES:
        summary = run.region_summaries.get(code)
        nums.add(Decimal(summary.key_count) if summary else Decimal(0))
        if summary:
            nums.add(summary.billed_amount)
    nums.update(_date_numbers(run.run_time))
    for finding in [*run.findings, *run.resolved]:
        nums.add(finding.billed_amount)
        if finding.nights_persisted is not None:
            nums.add(Decimal(finding.nights_persisted))
        nums.update(_date_numbers(finding.first_seen))
        nums.update(r.amount for r in finding.records if r.amount is not None)
    # Notes cite only evidence numbers, checked when the run was made (Req 10.2).
    nums.update(Decimal(n) for note in run.notes for n in note.numbers)
    return nums


# --- Morning report -----------------------------------------------------------------------------------------------


def date_text(dt: datetime | None) -> str:
    """``06 Nov 2026`` in UTC."""
    if dt is None:
        return ""
    d = dt.astimezone(UTC) if dt.tzinfo is not None else dt
    return f"{d.day:02d} {_MONTHS[d.month - 1]} {d.year}"


def _nights_text(n: int | None) -> str:
    if n is None:
        return ""
    return f"{n} night" if n == 1 else f"{n} nights"


def _rank(finding: Finding) -> tuple[int, int, str]:
    return (0 if finding.status == "new" else 1, DISPLAY_ORDER.index(finding.region_code), finding.key)


REPORT_CSS = """\
@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
html { background: #fff; color: #10141f; }
body { margin: 0 auto; max-width: 186mm; padding: 8mm 0; font: 9.5pt/1.4 system-ui, "Segoe UI", sans-serif; }
.mono, table, .brand, .night, dl { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; }
.brand { margin: 0; font-size: 8pt; letter-spacing: 0.3em; color: #1e5c3a; }
h1 { margin: 1mm 0 0; font-size: 14pt; }
.night { margin: 0 0 4mm; font-size: 8.5pt; color: #3c4252; }
.recorded { font-weight: 600; }
.headline { margin: 0 0 4mm; font-size: 12.5pt; line-height: 1.35; max-width: 40em; }
.notes { margin: -2mm 0 4mm; padding-left: 5mm; max-width: 44em; }
h2 { margin: 4mm 0 1mm; font: 600 8pt ui-monospace, Consolas, monospace; letter-spacing: 0.2em; color: #1e5c3a;
  text-transform: uppercase; border-bottom: 0.3mm solid #1e5c3a; padding-bottom: 0.6mm; }
table { width: 100%; border-collapse: collapse; font-size: 8.3pt; }
th { text-align: left; font-weight: 600; color: #1e5c3a; padding: 0.8mm 1.5mm; }
td { padding: 0.8mm 1.5mm; vertical-align: top; overflow-wrap: anywhere; }
tbody tr:nth-child(odd) { background: #e8f5ec; }
.num { text-align: right; white-space: nowrap; }
.new { font-weight: 600; }
dl { margin: 0; font-size: 8.3pt; }
dl div { display: flex; gap: 4mm; padding: 0.6mm 1.5mm; }
dl div:nth-child(odd) { background: #e8f5ec; }
dt { min-width: 52mm; color: #1e5c3a; }
dd { margin: 0; overflow-wrap: anywhere; }
.note { color: #3c4252; }
footer { margin-top: 4mm; }
"""


def report_csp() -> str:
    """The report's own policy: nothing loads, and only its one style block applies (Req 7.1, 11.2)."""
    digest = base64.b64encode(hashlib.sha256(REPORT_CSS.encode("utf-8")).digest()).decode("ascii")
    return (
        f"default-src 'none'; style-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )


def _e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def report_html(run: RunResult, recorded: bool = False) -> str:
    """A one-page, self-contained morning report of a run (Req 7.1). Every value is escaped (Req 7.3)."""
    view = run_view(run)
    ui = run.ui
    title = run.control_title or run.control_id or ui.title
    when = f"{date_text(run.run_time)}, {run.run_time.astimezone(UTC):%H:%M} UTC"
    parts: list[str] = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Night Audit morning report: {_e(title)}, {_e(date_text(run.run_time))}</title>",
        f"<style>{REPORT_CSS}</style></head><body>",
        f'<header><p class="brand">NIGHT AUDIT · MORNING REPORT · {_e(ui.title.upper())}</p>',
        f"<h1>{_e(title)}</h1>",
        f'<p class="night">Night of {_e(when)} · run {_e(run.run_id)}',
    ]
    if recorded:
        parts.append(f' · <span class="recorded">{_e(RECORDED_TEXT)}</span>')
    parts.append("</p></header>")
    parts.append(f'<p class="headline">{_e(view.headline)}</p>')
    if run.notes:
        parts.append('<ul class="notes">' + "".join(f"<li>{_e(n.text)}</li>" for n in run.notes) + "</ul>")
    key_label = next((c.label for c in ui.columns if c.from_ == "key"), "Key")
    count_label = ui.noun.plural[:1].upper() + ui.noun.plural[1:] if ui.noun.plural else "Keys"

    # Counts per region.
    parts.append(
        '<h2>Regions</h2><table class="regions"><thead><tr><th scope="col">Region</th>'
        f'<th scope="col">Code</th><th scope="col" class="num">{_e(count_label)}</th>'
        '<th scope="col" class="num">Billed</th></tr></thead><tbody>'
    )
    for code in DISPLAY_ORDER:
        summary = run.region_summaries.get(code)
        count = summary.key_count if summary else 0
        amount = money_text(summary.billed_amount) if summary and "B" in code else ""
        parts.append(
            f"<tr><td>{_e(run.region_names.get(code, code))}</td><td>{code}</td>"
            f'<td class="num">{count}</td><td class="num">{_e(amount)}</td></tr>'
        )
    parts.append("</tbody></table>")

    # Findings, new first.
    findings = sorted(_findings(run), key=_rank)
    parts.append(f"<h2>Findings · {len(findings)}</h2>")
    if findings:
        parts.append(
            '<table class="findings"><thead><tr><th scope="col">Status</th><th scope="col">Region</th>'
            f'<th scope="col">{_e(key_label)}</th><th scope="col">First seen</th>'
            '<th scope="col" class="num">Nights</th>'
            '<th scope="col" class="num">Billed</th></tr></thead><tbody>'
        )
        for f in findings:
            status = "New tonight" if f.status == "new" else "Persisting"
            billed = money_text(f.billed_amount) if "B" in f.region_code else "not billed"
            parts.append(
                f'<tr class="{"new" if f.status == "new" else "old"}"><td>{status}</td><td>{_e(f.name)}</td>'
                f'<td class="key">{_e(f.key)}</td><td>{_e(date_text(f.first_seen))}</td>'
                f'<td class="num">{_e(f.nights_persisted if f.nights_persisted is not None else "")}</td>'
                f'<td class="num">{_e(billed)}</td></tr>'
            )
        parts.append("</tbody></table>")
    else:
        parts.append("<p>No findings.</p>")

    resolved = sorted((f for f in run.resolved if not f.informational), key=_rank)
    if resolved:
        parts.append(f"<h2>Laid to rest · {len(resolved)}</h2>")
        parts.append(
            '<table class="resolved"><thead><tr><th scope="col">Region</th>'
            f'<th scope="col">{_e(key_label)}</th>'
            '<th scope="col">First seen</th><th scope="col" class="num">Lasted</th></tr></thead><tbody>'
        )
        for f in resolved:
            parts.append(
                f'<tr><td>{_e(f.name)}</td><td class="key">{_e(f.key)}</td>'
                f"<td>{_e(date_text(f.first_seen))}</td>"
                f'<td class="num">{_e(_nights_text(f.nights_persisted))}</td></tr>'
            )
        parts.append("</tbody></table>")

    parts.append("<h2>Money</h2><dl>")
    for line in view.lines:
        note = f' <span class="note">{_e(line.note)}</span>' if line.note else ""
        parts.append(f"<div><dt>{_e(line.label)}</dt><dd>{_e(line.value)}{note}</dd></div>")
    if not view.lines:
        parts.append("<div><dt>Billed</dt><dd>Not matched tonight.</dd></div>")
    parts.append("</dl>")

    parts.append("<footer><h2>Evidence</h2><dl>")
    chain = _e(run.evidence_chain_hash or "none")
    parts.append(f'<div><dt>Evidence chain hash</dt><dd class="mono">{chain}</dd></div>')
    parts.append(f'<div><dt>Control hash</dt><dd class="mono">{_e(run.control_hash)}</dd></div>')
    parts.append("<div><dt>Check it</dt><dd>nightaudit verify &lt;evidence pack&gt;</dd></div>")
    parts.append("</dl></footer></body></html>\n")
    return "".join(parts)


__all__ = [
    "CALM_HEADLINE",
    "RECORDED_TEXT",
    "MoneyLine",
    "RunView",
    "date_text",
    "headline",
    "headline_sentences",
    "ledger_key_counts",
    "money_text",
    "report_csp",
    "report_html",
    "run_numbers",
    "run_view",
]
