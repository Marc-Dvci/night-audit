"""The access review campaign: export a sheet, import the reviewer's decisions, verify them (Req 5).

``python -m ghosts.review export <run>`` writes ``review.csv`` and ``review.html`` with one line per finding.
``python -m ghosts.review import <run> <sheet.csv> --reviewer "<name>"`` records the decisions.
``python -m ghosts.review verify <run>`` checks the evidence pack and the decisions.

``<run>`` is a run directory or a run id under ``--runs``. Decisions go to ``<run>/evidence/decisions.jsonl``, a hash
chain of its own whose first link is the run's final evidence chain hash, so each decision is bound to the evidence it
was made on. A sheet is validated as a whole before anything is written, and a decision on a key the run did not
report is refused.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import io
import sys
from datetime import date
from pathlib import Path
from typing import Any

from nightaudit.decisions import (
    DECISIONS_FILE,
    DecisionChain,
    decision_row_hash,
    pack_problem,
    verify_decision_chain,
)
from nightaudit.evidence import canonical_json
from nightaudit.models import Finding, RunResult

from .connectors import Clock, system_clock

DECISIONS: tuple[str, ...] = ("keep", "revoke", "investigate")
REGION_ORDER: tuple[str, ...] = ("OB", "B", "IB", "I", "O")
COLUMNS: tuple[str, ...] = (
    "person", "region", "region_code", "systems", "seats", "left_on", "last_sign_in", "manager",
    "decision", "decision_date", "run_id", "evidence_chain_hash",
)
#: A cell starting with one of these is a formula to a spreadsheet; it is exported with a leading apostrophe.
FORMULA_START: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")
MAX_REVIEWER = 200


__all__ = ["DECISIONS_FILE", "DecisionVerdict", "ReviewError", "export", "import_sheet", "verify_decisions"]


class ReviewError(ValueError):
    """A sheet or a run that cannot be used, with a message for the reviewer."""


# --- Runs -------------------------------------------------------------------------------------------------------------


def locate_run(run: str, runs: Path) -> Path:
    """The run directory for a path or a run id."""
    for candidate in (Path(run), runs / run):
        if (candidate / "result.json").is_file():
            return candidate
    raise ReviewError(f"no run '{run}': give a run directory or a run id under {runs}")


def load_result(run_dir: Path) -> RunResult:
    return RunResult.model_validate_json((run_dir / "result.json").read_text(encoding="utf-8"))


def reported(result: RunResult) -> dict[str, Finding]:
    """The findings a reviewer decides on: every non-informational finding, by key."""
    return {f.key: f for f in result.findings if not f.informational}


def _rank(f: Finding) -> tuple[int, str]:
    return (REGION_ORDER.index(f.region_code) if f.region_code in REGION_ORDER else 99, f.key)


def review_rows(result: RunResult) -> list[dict[str, str]]:
    """One row per finding with the columns of Req 5.1; decision and date are empty."""
    rows: list[dict[str, str]] = []
    for f in sorted(reported(result).values(), key=_rank):
        c = f.context
        rows.append({
            "person": f.key,
            "region": f.name,
            "region_code": f.region_code,
            "systems": c.get("systems", ""),
            "seats": c.get("seats", ""),
            "left_on": c.get("left_on") or c.get("leaving_on", ""),
            "last_sign_in": c.get("last_sign_in", ""),
            "manager": c.get("manager", ""),
            "decision": "",
            "decision_date": "",
            "run_id": result.run_id,
            "evidence_chain_hash": result.evidence_chain_hash or "",
        })
    return rows


# --- Export (Req 5.1) -------------------------------------------------------------------------------------------------


def neutralise(cell: str) -> str:
    """Make a cell that a spreadsheet would run as a formula read as text.

    A cell that already starts with an apostrophe is prefixed too, so ``restore`` can tell the two apart.
    """
    return "'" + cell if cell.startswith((*FORMULA_START, "'")) else cell


def restore(cell: str) -> str:
    """Undo ``neutralise`` exactly: drop the apostrophe only where export added it."""
    return cell[1:] if cell.startswith("'") and cell[1:].startswith((*FORMULA_START, "'")) else cell


def sheet_csv(result: RunResult) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\r\n")
    writer.writeheader()
    for row in review_rows(result):
        writer.writerow({k: neutralise(v) for k, v in row.items()})
    return buffer.getvalue()


SHEET_CSS = """\
body { margin: 2rem auto; max-width: 70rem; font: 14px/1.45 system-ui, "Segoe UI", sans-serif; color: #10141f; }
h1 { font-size: 1.3rem; margin: 0 0 .25rem; }
p, dl { margin: .25rem 0 1rem; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; color: #1e5c3a; border-bottom: 1px solid #1e5c3a; padding: .3rem .4rem; }
td { padding: .3rem .4rem; vertical-align: top; overflow-wrap: anywhere; }
tbody tr:nth-child(odd) { background: #e8f5ec; }
.mono { font-family: ui-monospace, Consolas, monospace; font-size: 12px; }
td.blank { min-width: 7rem; border-bottom: 1px solid #8a93a6; }
"""
HTML_LABELS: tuple[tuple[str, str], ...] = (
    ("person", "Person"), ("region", "Region"), ("systems", "Systems"), ("seats", "Seats"),
    ("left_on", "Leaving date"), ("last_sign_in", "Last sign-in"), ("manager", "Manager"),
    ("decision", "Decision"), ("decision_date", "Date"),
)


def sheet_csp() -> str:
    """Nothing loads; only the sheet's own style block applies."""
    digest = base64.b64encode(hashlib.sha256(SHEET_CSS.encode("utf-8")).digest()).decode("ascii")
    return f"default-src 'none'; style-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"


def _e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def sheet_html(result: RunResult) -> str:
    """The review sheet as a self-contained page. Every value is escaped."""
    rows = review_rows(result)
    title = result.control_title or result.control_id or "Access review"
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="{_e(sheet_csp())}">',
        f"<title>Access review: {_e(title)}, run {_e(result.run_id)}</title>",
        f"<style>{SHEET_CSS}</style></head><body>",
        f"<h1>Access review: {_e(title)}</h1>",
        f'<p>Run <span class="mono">{_e(result.run_id)}</span>, '
        f"{_e(result.run_time.isoformat())}. {len(rows)} {'finding' if len(rows) == 1 else 'findings'} to decide.</p>",
        f'<p>Evidence chain hash <span class="mono">{_e(result.evidence_chain_hash or "none")}</span></p>',
        f"<p>Decide each line as one of: {_e(', '.join(DECISIONS))}. Record decisions in review.csv and import it.</p>",
        "<table><thead><tr>",
        *(f'<th scope="col">{_e(label)}</th>' for _, label in HTML_LABELS),
        "</tr></thead><tbody>",
    ]
    for row in rows:
        cells = []
        for column, _ in HTML_LABELS:
            if column in ("decision", "decision_date"):
                cells.append('<td class="blank"></td>')
            else:
                cls = ' class="mono"' if column in ("person", "manager", "last_sign_in") else ""
                cells.append(f"<td{cls}>{_e(row[column])}</td>")
        parts.append("<tr>" + "".join(cells) + "</tr>")
    parts.append("</tbody></table></body></html>\n")
    return "".join(parts)


def export(run_dir: Path, out: Path | None = None) -> tuple[Path, Path]:
    """Write ``review.csv`` and ``review.html`` for a run and return their paths."""
    result = load_result(run_dir)
    folder = out or run_dir
    folder.mkdir(parents=True, exist_ok=True)
    csv_path, html_path = folder / "review.csv", folder / "review.html"
    csv_path.write_text(sheet_csv(result), encoding="utf-8", newline="")
    html_path.write_text(sheet_html(result), encoding="utf-8")
    return csv_path, html_path


# --- Decisions (Req 5.2) ----------------------------------------------------------------------------------------------
# The chain check lives in the skeleton (skeleton Req 10.7), so the page can show decisions it has verified itself.

DecisionVerdict = DecisionChain


def _decision_row_hash(row: dict[str, Any]) -> str:
    return decision_row_hash(row)


def _bound_result(run_dir: Path) -> RunResult:
    """The run, after checking its evidence pack verifies and ends at the hash the run recorded."""
    result = load_result(run_dir)
    problem = pack_problem(run_dir, result)
    if problem is not None:
        raise ReviewError(problem)
    return result


def verify_decisions(run_dir: Path) -> DecisionChain:
    """Check the evidence pack, then every decision: hashes, links, binding to the run, and the key it names."""
    return verify_decision_chain(run_dir, load_result(run_dir), DECISIONS)


def parse_sheet(text: str, result: RunResult) -> list[dict[str, str]]:
    """The decisions of a sheet, validated against the run. Raises ``ReviewError`` naming every bad row."""
    reader = csv.DictReader(io.StringIO(text))
    needed = {"person", "region_code", "decision", "decision_date", "run_id", "evidence_chain_hash"}
    missing = needed - set(reader.fieldnames or [])
    if missing:
        raise ReviewError(f"the sheet has no column {', '.join(sorted(missing))}")
    findings = reported(result)
    errors: list[str] = []
    decided: list[dict[str, str]] = []
    seen: set[str] = set()
    for line, row in enumerate(reader, start=2):
        cell = {k: restore(v or "") for k, v in row.items() if k is not None}
        person = cell.get("person", "").strip()
        decision = cell.get("decision", "").strip().lower()
        when = cell.get("decision_date", "").strip()
        if not decision and not when:
            continue
        shown = person[:120] or "(empty)"
        finding = findings.get(person)
        if finding is None:
            errors.append(f"line {line}: {shown} was not reported by run {result.run_id}; no decision can be recorded")
            continue
        if cell.get("region_code", "").strip() != finding.region_code:
            errors.append(f"line {line}: {shown} is {finding.region_code} in run {result.run_id}, "
                          f"not {cell.get('region_code', '')[:10]!r}")
        if cell.get("run_id", "").strip() != result.run_id or (
            cell.get("evidence_chain_hash", "").strip() != (result.evidence_chain_hash or "")
        ):
            errors.append(f"line {line}: {shown} comes from a sheet of another run")
        if decision not in DECISIONS:
            errors.append(f"line {line}: {shown}: decision must be one of {', '.join(DECISIONS)}")
        try:
            date.fromisoformat(when)
        except ValueError:
            errors.append(f"line {line}: {shown}: decision_date must be a date like 2026-11-05")
        if person in seen:
            errors.append(f"line {line}: {shown} is decided twice in this sheet")
        seen.add(person)
        decided.append({"key": person, "region_code": finding.region_code, "decision": decision,
                        "decision_date": when})
    if errors:
        raise ReviewError("the sheet was not imported:\n  " + "\n  ".join(errors))
    if not decided:
        raise ReviewError("the sheet has no decisions")
    return decided


def import_sheet(run_dir: Path, sheet: Path, reviewer: str, clock: Clock = system_clock) -> list[dict[str, Any]]:
    """Validate a completed sheet and append its decisions to the run's decision chain. Returns the rows written."""
    name = reviewer.strip()
    if not name:
        raise ReviewError("a reviewer name is required")
    if len(name) > MAX_REVIEWER:
        raise ReviewError(f"the reviewer name is longer than {MAX_REVIEWER} characters")
    result = _bound_result(run_dir)
    raw = sheet.read_bytes()
    decided = parse_sheet(raw.decode("utf-8-sig"), result)
    existing = verify_decisions(run_dir)
    if not existing.ok:
        raise ReviewError(f"the decisions already recorded do not verify, so none are added: {existing.detail}")
    prev = existing.head or result.evidence_chain_hash
    imported_at = clock().isoformat()
    sheet_sha = hashlib.sha256(raw).hexdigest()
    rows: list[dict[str, Any]] = []
    for offset, decision in enumerate(decided):
        row: dict[str, Any] = {
            "index": existing.count + offset,
            "prev_hash": prev,
            "type": "decision",
            "run_id": result.run_id,
            "evidence_chain_hash": result.evidence_chain_hash,
            **decision,
            "reviewer": name,
            "imported_at": imported_at,
            "sheet_sha256": sheet_sha,
        }
        row["row_hash"] = _decision_row_hash(row)
        prev = row["row_hash"]
        rows.append(row)
    with (run_dir / "evidence" / DECISIONS_FILE).open("ab") as handle:
        for row in rows:
            handle.write(canonical_json(row).encode("utf-8") + b"\n")
    return rows


# --- CLI --------------------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None, clock: Clock = system_clock) -> int:
    parser = argparse.ArgumentParser(prog="python -m ghosts.review", description="The access review campaign.")
    parser.add_argument("--runs", type=Path, default=Path("runs"), help="runs directory (default: runs)")
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export", help="write review.csv and review.html")
    ex.add_argument("run")
    ex.add_argument("--out", type=Path, help="output folder (default: the run directory)")
    im = sub.add_parser("import", help="record the decisions of a completed sheet")
    im.add_argument("run")
    im.add_argument("sheet", type=Path)
    im.add_argument("--reviewer", required=True)
    ve = sub.add_parser("verify", help="verify the evidence pack and the decisions")
    ve.add_argument("run")
    args = parser.parse_args(argv)
    try:
        run_dir = locate_run(args.run, args.runs)
        if args.command == "export":
            for path in export(run_dir, args.out):
                print(path)
            return 0
        if args.command == "import":
            rows = import_sheet(run_dir, args.sheet, args.reviewer, clock)
            print(f"recorded {len(rows)} {'decision' if len(rows) == 1 else 'decisions'} by {args.reviewer.strip()}")
            print(f"decision chain head {rows[-1]['row_hash']}")
            return 0
        verdict = verify_decisions(run_dir)
        print(f"{'OK' if verdict.ok else 'FAIL'}  {verdict.detail}")
        return 0 if verdict.ok else 1
    except ReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
