"""Night Audit: a three-way match for things an organisation pays for.

The ``nightaudit`` package is the reusable skeleton.  An application supplies
three connectors (one per ledger) and a control file; the skeleton handles
normalisation, matching, night-over-night state, the evidence pack, the
explanation guard, and the API that the UI reads.
"""

from __future__ import annotations

from .connectors import (
    Connector,
    CSVConnector,
    JSONLConnector,
    make_connector,
)
from .control import (
    ConnectorConfig,
    ControlConfig,
    ControlFile,
    LedgerConfig,
    RegionOverride,
    ScopeFilter,
    SummariserConfig,
    resolve_region,
)
from .decisions import DecisionChain, verify_decision_chain
from .evidence import VerifyResult, verify_evidence_pack, write_evidence_pack
from .explain import Explanation, ModelConfig, explain_finding
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
    RunNote,
    RunResult,
    UnkeyedRow,
)
from .normalisers import NormaliserRegistry, UnknownNormaliserError, normalise
from .runner import load_control_file, load_run, run_control, run_summary
from .scope import apply_scope
from .state import FindingState, StateStore, compare_findings
from .steps import ControlContext

__all__ = [
    # constants
    "DEFAULT_REGION_MEANINGS",
    "DEFAULT_REGION_NAMES",
    "DEFAULT_REGION_SEVERITIES",
    "FINDING_REGIONS",
    "INFORMATIONAL_REGIONS",
    "REGION_CODES",
    # models
    "Finding",
    "LedgerName",
    "LedgerSnapshot",
    "Record",
    "RegionSummary",
    "RunNote",
    "RunResult",
    "UnkeyedRow",
    # normalisers
    "NormaliserRegistry",
    "UnknownNormaliserError",
    "normalise",
    # control
    "ControlConfig",
    "ControlFile",
    "ConnectorConfig",
    "LedgerConfig",
    "RegionOverride",
    "ScopeFilter",
    "SummariserConfig",
    "resolve_region",
    # steps and decisions (Req 10.3, 10.7)
    "ControlContext",
    "DecisionChain",
    "verify_decision_chain",
    # scope / grace
    "apply_scope",
    "find_pending",
    # matcher
    "match",
    # state
    "FindingState",
    "StateStore",
    "compare_findings",
    # evidence
    "VerifyResult",
    "write_evidence_pack",
    "verify_evidence_pack",
    # explain
    "ModelConfig",
    "Explanation",
    "explain_finding",
    # connectors
    "Connector",
    "CSVConnector",
    "JSONLConnector",
    "make_connector",
    # runner
    "run_control",
    "load_control_file",
    "load_run",
    "run_summary",
]
