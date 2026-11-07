"""Pydantic v2 data model and region constants for Night Audit.

All money is ``decimal.Decimal``, never float.  Records are frozen.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Region constants -------------------------------------------------------

#: The seven non-empty subsets of {I, O, B} in I-O-B order.
REGION_CODES: tuple[str, ...] = ("IOB", "IO", "IB", "OB", "I", "O", "B")

#: Default short label for each region code: its meaning in a few plain words, short enough for the Venn diagram and
#: the region list on a phone. A person reads this first, everywhere (product rules).
DEFAULT_REGION_LABELS: dict[str, str] = {
    "IOB": "Matched",
    "IO": "Approved and present, not billed",
    "IB": "Approved and billed, not seen",
    "OB": "Exists and billed, never approved",
    "I": "Approved, but absent",
    "O": "Exists, never approved, not billed",
    "B": "Billed, never approved, not seen",
}

#: Default Halloween name for each region code (product glossary). Shown only as a small tag beside the label.
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


# --- UI vocabulary (ui-kit Req 1) --------------------------------------------


class NounUi(BaseModel):
    """What a control counts, in both forms."""

    singular: str = "item"
    plural: str = "items"


class LedgerUi(BaseModel):
    """A ledger's short label and the sentence saying where its rows come from."""

    label: str
    source: str


class ColumnUi(BaseModel):
    """One column of the finding rows. ``from`` is key, name, status, amount, attr:<name> or context:<name>."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    label: str
    from_: str = Field(alias="from")

    @field_validator("from_")
    @classmethod
    def _known_source(cls, value: str) -> str:
        if value in {"key", "name", "status", "amount"}:
            return value
        prefix, _, name = value.partition(":")
        if prefix in {"attr", "context"} and name:
            return value
        raise ValueError(f"column 'from: {value}' must be key, name, status, amount, attr:<name> or context:<name>")


class HeadlineUi(BaseModel):
    """A headline template in singular (``one``) and plural (``other``) form."""

    one: str
    other: str


class UnkeyedUi(BaseModel):
    """What the billed lines with no key are called, and why they are kept apart (Req 10.4)."""

    singular: str = "line with no resource id"
    plural: str = "lines with no resource id"
    explanation: str = "Tax, credits and support lines carry no resource id, so they are kept apart."


#: A download is a plain file name in the run's folder: no separator, no ``..``, no hidden file, a short list of types.
DOWNLOAD_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.(csv|html|json|txt)$")


class DownloadUi(BaseModel):
    """A file beside the run that the page links to (Req 10.6)."""

    label: str = Field(min_length=1, max_length=80)
    file: str

    @field_validator("file")
    @classmethod
    def _plain_file_name(cls, value: str) -> str:
        if not DOWNLOAD_FILE.fullmatch(value):
            raise ValueError(
                f"download file '{value[:80]}' must be a plain name like review.csv (letters, digits, '-', '_'; "
                "csv, html, json or txt)"
            )
        return value


class RunNote(BaseModel):
    """A sentence an application adds to the run, with the numbers it cites (Req 10.2). Part of the evidence chain."""

    text: str
    numbers: list[str] = Field(default_factory=list)
    source: str = ""


DEFAULT_TAGLINE = "Three ledgers of the same reality, matched every night."

DEFAULT_LEDGER_UI: dict[str, LedgerUi] = {
    "intended": LedgerUi(label="Intended", source="What was approved."),
    "observed": LedgerUi(label="Observed", source="What exists."),
    "billed": LedgerUi(label="Billed", source="What is paid for."),
}

DEFAULT_COLUMNS: tuple[ColumnUi, ...] = (
    ColumnUi.model_validate({"label": "Key", "from": "key"}),
    ColumnUi.model_validate({"label": "Since", "from": "status"}),
    ColumnUi.model_validate({"label": "Billed", "from": "amount"}),
)


class UiConfig(BaseModel):
    """The resolved words a run renders with. Stored in every run so it renders the same forever (Req 1.3)."""

    title: str = "Night Audit"
    tagline: str = DEFAULT_TAGLINE
    noun: NounUi = Field(default_factory=NounUi)
    ledgers: dict[str, LedgerUi] = Field(default_factory=lambda: dict(DEFAULT_LEDGER_UI))
    columns: list[ColumnUi] = Field(default_factory=lambda: list(DEFAULT_COLUMNS))
    headlines: dict[str, HeadlineUi] = Field(default_factory=dict)
    unkeyed: UnkeyedUi = Field(default_factory=UnkeyedUi)
    downloads: list[DownloadUi] = Field(default_factory=list)


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
    #: Each region's short plain label. Runs saved before labels existed load empty; readers fall back to the defaults.
    region_labels: dict[str, str] = Field(default_factory=dict)
    region_meanings: dict[str, str] = Field(default_factory=dict)
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
    #: The control's resolved ``ui`` words. Runs saved before the UI kit load with the neutral defaults.
    ui: UiConfig = Field(default_factory=UiConfig)
    #: Sentences the control's summarisers added, each checked against the run's evidence numbers (Req 10.2).
    notes: list[RunNote] = Field(default_factory=list)
