"""Enricher: the HR facts and the per-person summaries a reviewer reads (Req 2.2, 5.1).

The skeleton merges what this returns into ``finding.context``, which is part of each finding's evidence row. It
cannot change a region: regions are decided before enrichers run.

The skeleton calls enrichers with ``(findings, options)`` only. It passes neither the control's directory nor its alias
domains, so a relative ``roster`` path resolves against ``apps/ghosts/controls/`` and the control repeats its alias
table in the options.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nightaudit.models import Finding, LedgerName
from nightaudit.normalisers import normalise

from .connectors import parse_time, read_csv

#: Where the shipped controls live; relative enricher paths resolve here.
CONTROLS_DIR = Path(__file__).resolve().parents[2] / "controls"


def _roster_by_key(path: Path, alias_domains: dict[str, str]) -> dict[str, dict[str, str]]:
    """Roster rows by normalised email. A person on the roster twice (a rehire) is read from the latest start."""
    ctx: dict[str, Any] = {"alias_domains": alias_domains}
    rows: dict[str, dict[str, str]] = {}
    for row in read_csv(path):
        key = normalise(row.get("email", ""), ["email_canonical"], ctx)
        if not key:
            continue
        held = rows.get(key)
        if held is None or row.get("start_date", "") >= held.get("start_date", ""):
            rows[key] = row
    return rows


def _joined(values: set[str]) -> str:
    return ", ".join(sorted(v for v in values if v))


def _latest_sign_in(values: list[str]) -> str:
    dated = [(t, v) for v in values if v and (t := parse_time(v, "last_sign_in")) is not None]
    return max(dated)[1] if dated else ""


def person_context(finding: Finding, row: dict[str, str] | None) -> dict[str, str]:
    """The context of one finding, from its own records and its roster row (``None`` when not on the roster)."""
    observed = [r for r in finding.records if r.ledger == LedgerName.observed]
    billed = [r for r in finding.records if r.ledger == LedgerName.billed]
    intended = any(r.ledger == LedgerName.intended for r in finding.records)
    context: dict[str, str] = {
        "systems": _joined({r.attrs.get("system", "") for r in observed}),
        "seats": _joined({r.attrs.get("vendor", "") for r in billed}),
        "last_sign_in": _latest_sign_in([r.attrs.get("last_sign_in", "") for r in observed]),
    }
    if row is None:
        context["hr_roster"] = "no record"
    else:
        name = " ".join(p for p in (row.get("given_name", ""), row.get("family_name", "")) if p)
        context.update(
            person=name,
            department=row.get("department", ""),
            manager=row.get("manager_email", ""),
            employment_type=row.get("employment_type", ""),
        )
        leaving = row.get("leaving_date", "")
        if intended:
            context["leaving_on"] = leaving  # still here on the run date
        elif leaving:
            context["left_on"] = leaving
        else:
            context["starts_on"] = row.get("start_date", "")  # on the roster, not started yet
    return {k: v for k, v in context.items() if v}


def people_context(findings: list[Finding], options: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Context for every finding the skeleton passes in, keyed by the finding's key."""
    roster = Path(str(options["roster"]))
    if not roster.is_absolute():
        roster = CONTROLS_DIR / roster
    alias_domains = {str(k): str(v) for k, v in (options.get("alias_domains") or {}).items()}
    rows = _roster_by_key(roster, alias_domains)
    return {f.key: person_context(f, rows.get(f.key)) for f in findings}
