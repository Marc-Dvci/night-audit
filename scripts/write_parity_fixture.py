"""Write the fixture the TypeScript tests compare against: canonical JSON, money text and evidence verdicts from Python.

``skeleton/web/test/fixtures/parity.json`` holds, for hostile inputs, what the Python implementation produces:

* ``canonical``: a value and ``evidence.canonical_json`` of it,
* ``money``: a decimal string as the API sends it and ``report.money_text`` of it,
* ``pack``: a hostile evidence pack (bidi overrides, astral characters, quotes, control characters, lone surrogates, row
  ids that sort differently by code point and by UTF-16 unit) and ``variants`` of it, each with Python's verdict, and
  ``displayed``: the run as a page shows it, edited in ways a page could lie (a fake finding, a changed region, a
  hidden finding, a changed figure), each with Python's verdict from comparing it with the untouched pack.

``skeleton/tests/test_parity_fixture.py`` fails when the committed file differs from what this script writes, so the
fixture always comes from the current Python code. Run: ``uv run python scripts/write_parity_fixture.py``.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from random import Random
from typing import Any

from nightaudit.api import run_document
from nightaudit.control import ControlConfig
from nightaudit.evidence import canonical_json, verify_evidence_pack, write_evidence_pack
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record, RegionSummary
from nightaudit.report import headline_money_text, headline_rounded, money_text

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "skeleton" / "web" / "test" / "fixtures" / "parity.json"
RUN_TIME = datetime(2026, 11, 6, 2, 0, tzinfo=UTC)

HOSTILE: list[str] = [
    "plain",
    'quote " and backslash \\ and slash /',
    "bidi \u202eevil\u202c and \u2066isolate\u2069 and \u200f",
    "astral \U0001f9db \U0001f47b \U00010000",
    "edge \uffff\ufffe\ufeff",
    "controls \x00\x01\x07\x08\t\n\x0b\x0c\r\x1b\x1f\x7f\x80\x9f",
    "lone \ud800 and \udfff surrogates",
    "accents caf\u00e9 \u00df \u0130",
    "<script>alert(1)</script>",
    "",
]
KEYS_BY_CODE_POINT: list[str] = ["Z", "a", "\u00e9", "\uffff", "\U00010000", "\U0001f600", "", "\ud800"]


def _canonical_cases() -> list[dict[str, Any]]:
    values: list[Any] = [None, True, False, 0, -7, 123456789012, *HOSTILE, [], {}, [1, "a", None, [True]]]
    values.append({k: i for i, k in enumerate(KEYS_BY_CODE_POINT)})
    values.append({"outer": {k: [k] for k in reversed(KEYS_BY_CODE_POINT)}, "b": HOSTILE})
    return [{"value": v, "canonical": canonical_json(v)} for v in values]


def _wire(value: Decimal) -> str:
    """The decimal string the API sends for an amount (pydantic's JSON form)."""
    return str(RegionSummary(code="B", key_count=0, billed_amount=value).model_dump(mode="json")["billed_amount"])


def _money_cases() -> list[dict[str, str]]:
    fixed = [
        "0",
        "-0",
        "0E-12",
        "1E+5",
        "0.5",
        "41.200",
        "0.000000001",
        "-3.10",
        "1234567.891",
        "-0.0000000001",
        "1E-30",
        "-7.25",
        "999",
        "1000",
        "100000000000000000000000000001",
        "0.59",
        "12.3456789012345678901234",
        "0.7172358001",
        "0.71725",
        "0.71735",
        "-0.71725",
        "0.0000000012345",
        "123.456",
        "12345.675",
        "9999.995",
        "0.99995",
    ]
    rnd = Random(20261106)
    generated = [
        f"{rnd.choice(['', '-'])}{rnd.randint(0, 10 ** rnd.randint(1, 30))}E{rnd.randint(-30, 6)}" for _ in range(60)
    ]
    cases = []
    for text in fixed + generated:
        value = Decimal(text)
        wire = _wire(value)
        cases.append(
            {"amount": wire, "text": money_text(Decimal(wire)), "headline": headline_money_text(Decimal(wire))}
        )
    return cases


def _hostile_snapshots() -> list[LedgerSnapshot]:
    old = datetime(2026, 9, 1, tzinfo=UTC)
    intended = [
        Record(
            ledger=LedgerName.intended,
            source="stacks",
            row_id=f"i{n}",
            raw_key=f"k{n}",
            attrs={"Name": text, KEYS_BY_CODE_POINT[n % len(KEYS_BY_CODE_POINT)]: "x"},
        )
        for n, text in enumerate(HOSTILE[:6])
    ]
    observed = [
        Record(
            ledger=LedgerName.observed,
            source="inventory",
            row_id=row_id,
            raw_key=key,
            timestamp=old,
            attrs={"note": text},
        )
        for row_id, key, text in [
            ("\uffff-1", "k0", HOSTILE[2]),
            ("\U00010000-1", "k1", HOSTILE[3]),
            ("same", "k2", HOSTILE[5]),
            ("same", "ghost-\U0001f47b", HOSTILE[6]),
            ("o-\u202e", "k9", HOSTILE[1]),
        ]
    ]
    billed = [
        Record(
            ledger=LedgerName.billed,
            source="cur",
            row_id=f"b{n}",
            raw_key=key,
            amount=Decimal(amount),
            attrs={"usage": text},
        )
        for n, (key, amount, text) in enumerate(
            [
                ("k0", "18.61", HOSTILE[7]),
                ("k1", "0.000000001", HOSTILE[8]),
                ("k9", "41.20", HOSTILE[4]),
                ("phantom-\u00e9", "6.40", HOSTILE[2]),
                ("phantom-two", "0.7172358001", HOSTILE[0]),
                ("", "-3.10", "credit"),
            ]
        )
    ]
    return [
        LedgerSnapshot(name=LedgerName.intended, source="stacks", records=intended),
        LedgerSnapshot(name=LedgerName.observed, source="inventory", records=observed),
        LedgerSnapshot(name=LedgerName.billed, source="cur", records=billed),
    ]


def change_one_byte(jsonl: str) -> str:
    """The UI's "Change one byte" action, in Python: the middle record row's first raw_key character."""
    lines = jsonl.split("\n")
    records = [i for i, line in enumerate(lines) if '"type":"record"' in line]
    i = records[len(records) // 2]
    at = lines[i].index('"raw_key":"') + len('"raw_key":"')
    before = lines[i][at]
    lines[i] = lines[i][:at] + ("y" if before == "x" else "x") + lines[i][at + 1 :]
    return "\n".join(lines)


def _rehash(line: str) -> str:
    row = json.loads(line)
    row["raw_key"] = "rehashed"
    row.pop("row_hash")
    row["row_hash"] = hashlib.sha256((row["prev_hash"] + canonical_json(row)).encode()).hexdigest()
    return canonical_json(row)


def _flip_after(line: str, marker: str) -> str:
    """Change the one character after *marker* to a different hex digit."""
    at = line.index(marker) + len(marker)
    return line[:at] + ("1" if line[at] == "0" else "0") + line[at + 1 :]


def _variants(jsonl: str) -> list[tuple[str, str]]:
    lines = jsonl.split("\n")[:-1]

    def join(new: list[str]) -> str:
        return "\n".join(new) + "\n"

    def at(i: int, line: str) -> str:
        return join(lines[:i] + [line] + lines[i + 1 :])

    last = len(lines) - 1
    bidi = next(i for i, line in enumerate(lines) if "\\u202e" in line)
    return [
        ("untouched", jsonl),
        ("change one byte", change_one_byte(jsonl)),
        ("one extra space", at(2, lines[2].replace('":', '": ', 1))),
        ("escaped bidi written raw", at(bidi, lines[bidi].replace("\\u202e", "\u202e", 1))),
        ("prev_hash digit", at(last, _flip_after(lines[last], '"prev_hash":"'))),
        ("row_hash digit", at(3, _flip_after(lines[3], '"row_hash":"'))),
        ("rehashed row", at(4, _rehash(lines[4]))),
        ("rows swapped", join([lines[1], lines[0], *lines[2:]])),
        ("last row removed", join(lines[:-1])),
        ("truncated line", at(5, lines[5][:-1])),
        ("no trailing newline", jsonl[:-1]),
    ]


def _verdict(jsonl: str, manifest: str, displayed: dict[str, Any] | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp)
        (pack / "evidence.jsonl").write_bytes(jsonl.encode("utf-8", "surrogatepass"))
        (pack / "manifest.json").write_text(manifest, encoding="utf-8")
        result = verify_evidence_pack(pack, displayed)
    return {
        "ok": result.ok,
        "failed_row": result.failed_row,
        "rows": result.rows,
        "findings": result.findings,
        "final_hash": result.final_hash,
        "detail": result.detail,
    }


def _displayed_variants(shown: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The page as served, and edits of it. Every variant is a deep copy, so the edits do not touch each other."""

    def edit(name: str, change: Callable[[dict[str, Any]], None]) -> tuple[str, dict[str, Any]]:
        copy: dict[str, Any] = json.loads(json.dumps(shown))
        change(copy)
        return name, copy

    def fake(d: dict[str, Any]) -> None:
        extra = json.loads(json.dumps(d["findings"][0]))
        extra["key"] = "fake-\u202e\U0001f47b-\u00e9"
        d["findings"].append(extra)

    def region(d: dict[str, Any]) -> None:
        d["findings"][0]["region_code"] = "IOB"

    def status(d: dict[str, Any]) -> None:
        d["findings"][0]["status"] = "persisting"

    def amount(d: dict[str, Any]) -> None:
        d["findings"][0]["billed_amount"] = "0.000000002"

    def count(d: dict[str, Any]) -> None:
        d["region_summaries"][d["findings"][0]["region_code"]]["key_count"] += 1

    def headline_count(d: dict[str, Any]) -> None:
        d["view"]["finding_count"] += 1

    def billed_total(d: dict[str, Any]) -> None:
        d["billed_total"] = "1E+30"

    def run_time_offset(d: dict[str, Any]) -> None:
        d["run_time"] = "2026-11-06T04:00:00+02:00"

    return [
        ("served as it is", shown),
        edit("a fake finding", fake),
        edit("a changed region", region),
        edit("a changed status", status),
        edit("a changed billed amount", amount),
        edit("a hidden finding", lambda d: d["findings"].pop(0)),
        edit("a finding shown twice", lambda d: d["findings"].append(d["findings"][0])),
        edit("a changed region count", count),
        edit("a changed headline count", headline_count),
        edit("a changed billed total", billed_total),
        edit("a changed run id", lambda d: d.update(run_id="0123456789abcdef")),
        edit("a changed chain hash", lambda d: d.update(evidence_chain_hash="0" * 64)),
        edit("no findings list", lambda d: d.pop("findings")),
        edit("the same run time written with an offset", run_time_offset),
        edit("marked incomplete while it states amounts", lambda d: d.update(complete=False)),
        edit("marked incomplete with no bill, findings still shown", hide_the_bill),
        edit("no completeness flag", lambda d: d.pop("complete")),
        edit("a headline amount rounded wrongly", lambda d: _headline_amount(d, "B", lambda a: _off_by_one(a))),
        edit("a headline amount written exactly", lambda d: _headline_amount(d, "B", money_text)),
        edit("a finding amount rounded like the headline", lambda d: _round_finding(d, "phantom-two")),
    ]


def _off_by_one(amount: Decimal) -> str:
    """The headline's text for *amount* with its last digit one higher: a rounding no rule gives."""
    rounded = headline_money_text(amount)
    return rounded[:-1] + str((int(rounded[-1]) + 1) % 10)


def _headline_amount(d: dict[str, Any], code: str, text: Callable[[Decimal], str]) -> None:
    amount = Decimal(d["region_summaries"][code]["billed_amount"])
    printed = headline_money_text(amount)
    assert any(printed in s for s in d["view"]["headline_sentences"]), printed
    d["view"]["headline_sentences"] = [s.replace(printed, text(amount)) for s in d["view"]["headline_sentences"]]
    d["view"]["headline"] = d["view"]["headline"].replace(printed, text(amount))


def _round_finding(d: dict[str, Any], key: str) -> None:
    finding = next(f for f in d["findings"] if f["key"] == key)
    finding["billed_amount"] = str(headline_rounded(Decimal(finding["billed_amount"])))


def hide_the_bill(d: dict[str, Any]) -> None:
    """A complete night's page edited to say it was incomplete and billed nothing, its findings still on it."""
    d.update(complete=False, billed_total="0", billed_unkeyed="0")
    d["view"].update(billed_total="0", unkeyed_total="0", keyed_total="0")


def _without_completeness(jsonl: str, manifest: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The same pack as written before the header recorded ``complete``: the field gone, the chain rehashed."""
    prev, lines = "0" * 64, []
    for line in jsonl.split("\n")[:-1]:
        row = json.loads(line)
        row.pop("complete", None)
        row.pop("row_hash")
        row["prev_hash"] = prev
        row["row_hash"] = hashlib.sha256((prev + canonical_json(row)).encode()).hexdigest()
        prev = row["row_hash"]
        lines.append(canonical_json(row))
    rest = {k: v for k, v in manifest.items() if k != "complete"}
    return "\n".join(lines) + "\n", {**rest, "final_chain_hash": prev}


def _incomplete_snapshots() -> list[LedgerSnapshot]:
    """The hostile night with its observed ledger unread: the chain keeps the intended and billed rows."""
    return [
        s.model_copy(update={"records": [], "missing": True}) if s.name is LedgerName.observed else s
        for s in _hostile_snapshots()
    ]


def _page(result: Any, final_hash: str) -> dict[str, Any]:
    page = result.model_copy(
        update={"snapshots": [], "findings": [f.model_copy(update={"records": []}) for f in result.findings]}
    )
    shown: dict[str, Any] = json.loads(json.dumps(run_document(page)))
    shown["evidence_chain_hash"] = final_hash
    return shown


def _completeness_cases(jsonl: str, manifest: dict[str, Any], shown: dict[str, Any]) -> list[dict[str, Any]]:
    """Completeness against the chain: an incomplete night, and packs written before the chain recorded it."""
    result = match(_incomplete_snapshots(), ControlConfig(), RUN_TIME)
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp)
        write_evidence_pack(result, pack)
        inc_jsonl = (pack / "evidence.jsonl").read_text(encoding="utf-8")
        inc_manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    inc_shown = _page(result, inc_manifest["final_chain_hash"])
    old_jsonl, old_manifest = _without_completeness(jsonl, manifest)
    old_inc_jsonl, old_inc_manifest = _without_completeness(inc_jsonl, inc_manifest)
    old_shown = {**shown, "evidence_chain_hash": old_manifest["final_chain_hash"]}
    old_inc_shown = {**inc_shown, "evidence_chain_hash": old_inc_manifest["final_chain_hash"]}
    hidden = json.loads(json.dumps(old_shown))
    hide_the_bill(hidden)
    marked_complete = {**inc_shown, "complete": True}
    pre_jsonl, pre_manifest = _legacy_pack(jsonl, {k: v for k, v in manifest.items() if k != "complete"})
    pre_shown = {**shown, "evidence_chain_hash": pre_manifest["final_chain_hash"]}
    pre_hidden = json.loads(json.dumps(pre_shown))
    hide_the_bill(pre_hidden)
    cases = [
        ("an incomplete night served as it is", inc_jsonl, inc_manifest, inc_shown),
        ("an incomplete night marked complete", inc_jsonl, inc_manifest, marked_complete),
        ("before completeness: a complete night", old_jsonl, old_manifest, old_shown),
        ("before completeness: an incomplete night", old_inc_jsonl, old_inc_manifest, old_inc_shown),
        ("before completeness: a complete night marked incomplete with no bill", old_jsonl, old_manifest, hidden),
        ("before the header (the lab night's shape): a complete night", pre_jsonl, pre_manifest, pre_shown),
        ("before the header: a complete night marked incomplete with no bill", pre_jsonl, pre_manifest, pre_hidden),
    ]
    return [
        {"name": name, "jsonl": text, "manifest": m, "document": doc, "verdict": _verdict(text, json.dumps(m), doc)}
        for name, text, m, doc in cases
    ]


def _legacy_pack(jsonl: str, manifest: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The same pack as written before the header row existed: no header, a chain that starts at the seed."""
    rows = [json.loads(line) for line in jsonl.split("\n")[:-1]][1:]
    prev, lines = "0" * 64, []
    for index, row in enumerate(rows):
        row.pop("row_hash")
        row.update(index=index, prev_hash=prev)
        row["row_hash"] = hashlib.sha256((prev + canonical_json(row)).encode()).hexdigest()
        prev = row["row_hash"]
        lines.append(canonical_json(row))
    return "\n".join(lines) + "\n", {**manifest, "final_chain_hash": prev, "row_count": len(rows)}


def _pack_case() -> dict[str, Any]:
    result = match(_hostile_snapshots(), ControlConfig(), RUN_TIME)
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp)
        write_evidence_pack(result, pack)
        jsonl = (pack / "evidence.jsonl").read_text(encoding="utf-8")
        manifest = (pack / "manifest.json").read_text(encoding="utf-8")
    # The page never holds a lone surrogate (pydantic cannot write one), and the comparison does not read the records.
    page = result.model_copy(
        update={"snapshots": [], "findings": [f.model_copy(update={"records": []}) for f in result.findings]}
    )
    shown = json.loads(json.dumps(run_document(page)))
    legacy_jsonl, legacy_manifest = _legacy_pack(jsonl, json.loads(manifest))
    return {
        "manifest": json.loads(manifest),
        "legacy": {
            "jsonl": legacy_jsonl,
            "manifest": legacy_manifest,
            "verdict": _verdict(legacy_jsonl, json.dumps(legacy_manifest)),
        },
        "variants": [
            {"name": name, "jsonl": text, "verdict": _verdict(text, manifest)} for name, text in _variants(jsonl)
        ],
        "displayed": [
            {"name": name, "document": document, "verdict": _verdict(jsonl, manifest, document)}
            for name, document in _displayed_variants(shown)
        ],
        "completeness": _completeness_cases(jsonl, json.loads(manifest), shown),
    }


def build() -> str:
    """The fixture file's exact text."""
    data = {"canonical": _canonical_cases(), "money": _money_cases(), "pack": _pack_case()}
    return json.dumps(data, indent=1) + "\n"


def main() -> int:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
