"""Run notes for the own-build control: say, above the findings, what the credit figures are and are not.

The sentences hold no numbers, so the skeleton's rule that a note cites only evidence numbers (audit rule 2) holds
trivially. The first one is always printed when any file was billed: the credits per file are an allocation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nightaudit.models import LedgerName, RunResult
from nightaudit.steps import ControlContext

from .connectors import parse_credits, read_csv

ALLOCATION = (
    "Credits per file are an allocation: each session's credits are split equally across the files it touched. "
    "They are not a measurement of what one file cost."
)
UNREPORTED = (
    "Some Kiro sessions were stopped before they reported credits, "
    "so their files carry zero credits and stay on the list."
)
UNALLOCATED = "Some credits were spent in sessions that touched no file, so no file carries them."
RELATIVE = (
    "A path in a spec is resolved against the files git tracks: the one tracked file it ends, or every tracked file "
    "under a folder. A path that ends no tracked file, or more than one, is kept as written, "
    "so it shows as promised and never built."
)


def credits_without_files(sessions_csv: Path) -> bool:
    """Whether any session reported credits and touched no file."""
    rows = read_csv(sessions_csv, ("session", "files_touched", "credits"))
    for row in rows:
        credits = parse_credits(row["credits"], "kiro-sessions.csv credits")
        if credits is not None and credits > 0 and row["files_touched"] in ("", "0"):
            return True
    return False


def allocation_notes(result: RunResult, options: dict[str, Any], control: ControlContext) -> list[str]:
    """The sentences about the allocation, the stopped sessions and the credits no file carries."""
    billed = [r for s in result.snapshots if s.name == LedgerName.billed for r in s.records]
    if not billed:
        return []
    notes = [ALLOCATION]
    if any(r.attrs.get("unreported_lines") for r in billed):
        notes.append(UNREPORTED)
    if any(code == "I" for code in result.regions.values()):
        notes.append(RELATIVE)
    sessions = options.get("sessions")
    if sessions and credits_without_files(control.resolve(str(sessions))):
        notes.append(UNALLOCATED)
    return notes
