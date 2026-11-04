"""Night Audit: a three-way match for things an organisation pays for.

The ``nightaudit`` package is the reusable skeleton.  An application supplies
three connectors (one per ledger) and a control file; the skeleton handles
normalisation, matching, night-over-night state, the evidence pack, the
explanation guard, and the API that the UI reads.
"""

from __future__ import annotations

from .control import (
    ConnectorConfig,
    ControlConfig,
    ControlFile,
    LedgerConfig,
    RegionOverride,
    ScopeFilter,
)
from .grace import find_pending
from .matcher import match
from .models import (
    DEFAULT_REGION_MEANINGS,
    DEFAULT_REGION_NAMES,
    DEFAULT_REGION_SEVERITIES,
    FINDING_REGIONS,
    INFORMATIONAL_REGIONS,
    REGION_CODES,
    Finding,
    LedgerName,
    LedgerSnapshot,
    Record,
    RegionSummary,
    RunResult,
    UnkeyedRow,
)
from .normalisers import NormaliserRegistry, UnknownNormaliserError, normalise
from .scope import apply_scope

__all__ = [
    "DEFAULT_REGION_MEANINGS",
    "DEFAULT_REGION_NAMES",
    "DEFAULT_REGION_SEVERITIES",
    "FINDING_REGIONS",
    "INFORMATIONAL_REGIONS",
    "REGION_CODES",
    "Finding",
    "LedgerName",
    "LedgerSnapshot",
    "Record",
    "RegionSummary",
    "RunResult",
    "UnkeyedRow",
    "NormaliserRegistry",
    "UnknownNormaliserError",
    "normalise",
    "ControlConfig",
    "ControlFile",
    "ConnectorConfig",
    "LedgerConfig",
    "RegionOverride",
    "ScopeFilter",
    "match",
    "apply_scope",
    "find_pending",
]
