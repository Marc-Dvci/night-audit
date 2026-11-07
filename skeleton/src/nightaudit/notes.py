"""Investigator's notes recorded against a run, and the check that lets the page show them (night shift Req 1.2).

The night shift (``scripts/night_shift.py``) asks an investigator agent for a short note on each new finding in the
regions ``OB`` and ``O``. Code decides whether a note may be kept: its numbers must all be in the finding's evidence
(the explanation guard's number check, audit rule 2). Every attempt that reached the guard is appended to
``<run>/evidence/notes.jsonl``, a hash chain built like ``decisions.jsonl``: each row is canonical JSON with ``index``,
``prev_hash``, ``row_hash``, ``run_id``, ``evidence_chain_hash``, ``key``, ``region_code``, ``verdict``
(``accepted`` or ``rejected``), ``text`` (empty when rejected), ``numbers``, ``reason`` (empty when accepted),
``model`` and ``at``. The first ``prev_hash`` is the run's final evidence chain hash and
``row_hash = SHA-256(prev_hash + canonical_json(row without row_hash))``, so every note is bound to the exact evidence
it was written about. The file is not part of the evidence chain: a run without notes verifies as before.

``verify_note_chain`` re-runs the number check on every accepted note. The page shows accepted notes only, and only
when the whole chain verifies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .decisions import decision_row_hash, pack_problem
from .evidence import canonical_json
from .explain import note_numbers, numbers_are_safe
from .models import RunResult

NOTES_FILE = "notes.jsonl"
#: The regions the investigator opens: a Vampire or a Ghost (``OB``) and a Poltergeist (``O``).
NOTE_REGIONS: tuple[str, ...] = ("OB", "O")
VERDICTS: tuple[str, ...] = ("accepted", "rejected")
MAX_NOTE_CHARS = 600
MAX_REASON_CHARS = 300
MAX_MODEL_CHARS = 100
#: Control characters, line and paragraph separators and bidi marks: a note is one plain line.
_UNSAFE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u200e\u200f\u202a-\u202e\u2066-\u2069]")


@dataclass
class NoteChain:
    """The verdict on a run's notes, and every row when the chain verifies."""

    ok: bool
    detail: str
    failed_row: int | None = None
    count: int = 0
    head: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)


def note_text_problem(text: str) -> str | None:
    """Why *text* cannot be a note (empty, too long, or not one plain line), or ``None``."""
    if not text.strip():
        return "the note is empty"
    if len(text) > MAX_NOTE_CHARS:
        return f"the note is longer than {MAX_NOTE_CHARS} characters"
    if _UNSAFE.search(text):
        return "the note holds a control or line-ending character"
    return None


def _read_lines(path: Path) -> list[bytes]:
    lines = path.read_bytes().split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return lines


def verify_note_chain(run_dir: Path, result: RunResult) -> NoteChain:
    """Check the evidence pack, then every note: bytes, index, link, hash, binding, the finding, and the guard."""
    problem = pack_problem(run_dir, result)
    if problem is not None:
        return NoteChain(False, problem)
    path = run_dir / "evidence" / NOTES_FILE
    if not path.exists():
        return NoteChain(True, "evidence verifies; no notes recorded", head=result.evidence_chain_hash)
    findings = {(f.key, f.region_code): f for f in result.findings if f.region_code in NOTE_REGIONS}
    lines = _read_lines(path)
    n = len(lines)
    prev = result.evidence_chain_hash
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(lines):
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return NoteChain(False, f"note {i}: not valid JSON", i, n)
        if not isinstance(row, dict):
            return NoteChain(False, f"note {i}: not a JSON object", i, n)
        if canonical_json(row).encode("utf-8") != raw:
            return NoteChain(False, f"note {i}: bytes differ from the canonical form", i, n)
        if row.get("index") != i:
            return NoteChain(False, f"note {i}: index is {row.get('index')!r}", i, n)
        if row.get("prev_hash") != prev:
            return NoteChain(False, f"note {i}: chain broken (prev_hash does not link)", i, n)
        if decision_row_hash(row) != row.get("row_hash"):
            return NoteChain(False, f"note {i}: hash mismatch", i, n)
        if row.get("run_id") != result.run_id or row.get("evidence_chain_hash") != result.evidence_chain_hash:
            return NoteChain(False, f"note {i}: bound to another run", i, n)
        finding = findings.get((str(row.get("key")), str(row.get("region_code"))))
        if finding is None:
            return NoteChain(False, f"note {i}: names a finding run {result.run_id} did not report", i, n)
        text, reason, model = row.get("text"), row.get("reason"), row.get("model")
        if not isinstance(text, str) or not isinstance(reason, str) or not isinstance(model, str) or not model:
            return NoteChain(False, f"note {i}: text, reason and model must be strings, model not empty", i, n)
        if not isinstance(row.get("at"), str):
            return NoteChain(False, f"note {i}: no time", i, n)
        verdict = row.get("verdict")
        if verdict == "accepted":
            bad = note_text_problem(text)
            if bad is not None or reason:
                return NoteChain(False, f"note {i}: {bad or 'an accepted note has a rejection reason'}", i, n)
            safe, offending = numbers_are_safe(text, finding)
            if not safe:
                cited = ", ".join(str(d) for d in offending)
                return NoteChain(False, f"note {i}: cites number(s) not in the evidence: {cited}", i, n)
            if row.get("numbers") != note_numbers(text):
                return NoteChain(False, f"note {i}: the numbers it lists are not the numbers it cites", i, n)
        elif verdict == "rejected":
            if text or not reason:
                return NoteChain(False, f"note {i}: a rejected note keeps no text and states a reason", i, n)
        else:
            return NoteChain(False, f"note {i}: unknown verdict", i, n)
        prev = str(row["row_hash"])
        rows.append(row)
    accepted = sum(1 for r in rows if r["verdict"] == "accepted")
    return NoteChain(True, f"evidence verifies; {n} notes verify ({accepted} accepted)", count=n, head=prev, rows=rows)


def append_note(
    run_dir: Path,
    result: RunResult,
    *,
    key: str,
    region_code: str,
    verdict: str,
    text: str,
    reason: str,
    model: str,
    at: datetime,
) -> dict[str, Any]:
    """Append one row to the run's notes chain and return it.

    Refuses when the evidence pack or the existing chain does not verify, so a broken chain is never extended.
    """
    chain = verify_note_chain(run_dir, result)
    if not chain.ok:
        raise ValueError(chain.detail)
    row: dict[str, Any] = {
        "index": chain.count,
        "prev_hash": chain.head,
        "run_id": result.run_id,
        "evidence_chain_hash": result.evidence_chain_hash,
        "key": key,
        "region_code": region_code,
        "verdict": verdict,
        "text": text if verdict == "accepted" else "",
        "numbers": note_numbers(text) if verdict == "accepted" else [],
        "reason": reason[:MAX_REASON_CHARS] if verdict == "rejected" else "",
        "model": model[:MAX_MODEL_CHARS],
        "at": at.isoformat(),
    }
    row["row_hash"] = decision_row_hash(row)
    with (run_dir / "evidence" / NOTES_FILE).open("ab") as handle:
        handle.write(canonical_json(row).encode("utf-8") + b"\n")
    return row


def page_notes(run_dir: Path, result: RunResult) -> dict[str, Any] | None:
    """What the page shows about notes: ``None`` without a notes file, else the verdict and, if it holds, accepted rows.

    A rejected note is never shown. A key noted twice shows its latest accepted note.
    """
    if not (run_dir / "evidence" / NOTES_FILE).exists():
        return None
    chain = verify_note_chain(run_dir, result)
    latest: dict[tuple[str, str], dict[str, str]] = {}
    for row in chain.rows if chain.ok else []:
        if row["verdict"] == "accepted":
            latest[(str(row["key"]), str(row["region_code"]))] = {
                "key": str(row["key"]),
                "region_code": str(row["region_code"]),
                "text": str(row["text"]),
                "model": str(row["model"]),
                "at": str(row["at"]),
            }
    return {"ok": chain.ok, "detail": chain.detail, "rows": [latest[k] for k in sorted(latest)]}
