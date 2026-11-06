"""Pydantic v2 data model and region constants for Night Audit.

All money is ``decimal.Decimal``, never float.  Records are frozen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Region constants -------------------------------------------------------

#: The seven non-empty subsets of {I, O, B} in I-O-B order.
REGION_CODES: tuple[str, ...] = ("IOB", "IO", "IB", "OB", "I", "O", "B")

#: Default monster name for each region code (product glossary).
DEFAULT_REGION_NAMES: dict[str, str] = {
    "IOB": "Living",
    "IO": "Familiar",
    "IB": "Wraith",
    "OB": "Vampire",
    "I": "Skeleton",
    "O": "Poltergeist",
    "B": "Phantom",
}

#: One-sentence meaning for each region code (product glossary).
DEFAULT_REGION_MEANINGS: dict[str, str] = {
    "IOB": "Matched. No finding.",
    "IO": "Approved and present, not billed. Informational.",
    "IB": "Approved and paid for, but not observed.",
    "OB": "Exists and is paid for, but nobody approved it.",
    "I": "Approved, but absent and unbilled.",
    "O": "Exists, unapproved, not billed.",
    "B": "Billed for something nobody approved and nobody can see.",
}

#: Default severity for each region code.
DEFAULT_REGION_SEVERITIES: dict[str, str] = {
    "IOB": "none",
    "IO": "informational",
    "IB": "high",
    "OB": "high",
    "I": "medium",
    "O": "low",
    "B": "high",
}

#: Keys in these regions are actionable findings.
FINDING_REGIONS: frozenset[str] = frozenset({"OB", "O", "B", "I", "IB"})

#: Keys in this region are informational (shown in UI, counted separately).
INFORMATIONAL_REGIONS: frozenset[str] = frozenset({"IO"})


# --- Enums ------------------------------------------------------------------


class LedgerName(str, Enum):
    """The three ledgers of a three-way match."""

    intended = "intended"
    observed = "observed"
    billed = "billed"


# --- Models -----------------------------------------------------------------


class Record(BaseModel):
    """One row from one ledger.

    ``key`` is ``None`` until the matcher applies the normaliser chain to
    ``raw_key``.  An empty normalised key means the record is *unkeyed* and
    excluded from matching.
    """

    model_config = ConfigDict(frozen=True)

    ledger: LedgerName
    source: str
    row_id: str
    raw_key: str
    key: str | None = None
    attrs: dict[str, str] = Field(default_factory=dict)
    amount: Decimal | None = None
    timestamp: datetime | None = None

    @field_validator("timestamp")
    @classmethod
    def _naive_timestamp_is_utc(cls, value: datetime | None) -> datetime | None:
        """A timestamp without an offset is UTC, the rule the built-in connectors already apply.

        Without it, one naive and one aware timestamp on the same key cannot be compared by the grace window.
        """
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class LedgerSnapshot(BaseModel):
    """The result of fetching one ledger."""

    name: LedgerName
    source: str
    records: list[Record] = Field(default_factory=list)
    dropped: int = 0
    missing: bool = False


class UnkeyedRow(BaseModel):
    """A record whose normalised key is empty, reported separately."""

    row_id: str
    ledger: LedgerName
    source: str
    amount: Decimal | None = None


class Finding(BaseModel):
    """One key that does not match (non-IOB), with all its evidence."""

    key: str
    region_code: str
    name: str
    severity: str
    meaning: str
    informational: bool
    records: list[Record] = Field(default_factory=list)
    billed_amount: Decimal = Decimal("0")
    duplicate_counts: dict[str, int] = Field(default_factory=dict)
    status: str = "new"
    nights_persisted: int | None = None
    first_seen: datetime | None = None
    explanation: str | None = None
    #: Read-only context gathered after matching (for example the creating CloudTrail event).
    context: dict[str, str] = Field(default_factory=dict)


class RegionSummary(BaseModel):
    """Aggregated stats for one region."""

    code: str
    key_count: int
    billed_amount: Decimal


class RunResult(BaseModel):
    """The complete output of one run."""

    run_id: str
    run_time: datetime
    control_hash: str
    complete: bool
    control_id: str = ""
    control_title: str = ""
    app: str = ""
    region_names: dict[str, str] = Field(default_factory=dict)
    ledger_errors: dict[str, str] = Field(default_factory=dict)
    excluded: dict[str, int] = Field(default_factory=dict)
    missing_ledgers: list[str] = Field(default_factory=list)
    snapshots: list[LedgerSnapshot] = Field(default_factory=list)
    regions: dict[str, str] = Field(default_factory=dict)
    pending_keys: list[str] = Field(default_factory=list)
    unkeyed: list[UnkeyedRow] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    region_summaries: dict[str, RegionSummary] = Field(default_factory=dict)
    duplicates: dict[str, dict[str, int]] = Field(default_factory=dict)
    billed_total: Decimal = Decimal("0")
    billed_unkeyed: Decimal = Decimal("0")
    dropped: dict[str, int] = Field(default_factory=dict)
    resolved: list[Finding] = Field(default_factory=list)
    evidence_chain_hash: str | None = None
