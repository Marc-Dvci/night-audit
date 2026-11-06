"""Control file schema, loading, validation, and canonical hash.

A control file declares three ledgers, their key fields and normalisers, the
grace window, scope filters, and optional region overrides.  ``ControlConfig``
is the subset the matcher needs; ``ControlFile`` adds connector configuration.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from .models import (
    DEFAULT_REGION_MEANINGS,
    DEFAULT_REGION_NAMES,
    DEFAULT_REGION_SEVERITIES,
)
from .normalisers import NormaliserRegistry, UnknownNormaliserError


def resolve_region(code: str, control: ControlConfig) -> tuple[str, str, str]:
    """Resolve ``(name, severity, meaning)`` from overrides or defaults (Req 1.4).

    Shared by the matcher, the state module and the explainer so the resolution
    rule lives in one place.
    """
    override = control.regions.get(code)
    if override is not None:
        name = override.name if override.name is not None else DEFAULT_REGION_NAMES[code]
        severity = (
            override.severity
            if override.severity is not None
            else DEFAULT_REGION_SEVERITIES[code]
        )
        meaning = (
            override.meaning
            if override.meaning is not None
            else DEFAULT_REGION_MEANINGS[code]
        )
    else:
        name = DEFAULT_REGION_NAMES[code]
        severity = DEFAULT_REGION_SEVERITIES[code]
        meaning = DEFAULT_REGION_MEANINGS[code]
    return name, severity, meaning


class ScopeFilter(BaseModel):
    """A record is in scope when ``attrs[attr] == equals``."""

    attr: str
    equals: str


class RegionOverride(BaseModel):
    """Optional override for a region's name, severity, meaning, or template."""

    name: str | None = None
    severity: str | None = None
    meaning: str | None = None
    template: str | None = None


class ControlConfig(BaseModel):
    """The subset of a control file that the matcher needs."""

    normalisers: dict[str, list[str]] = Field(default_factory=dict)
    grace_hours: int = 24
    scope: ScopeFilter | None = None
    alias_domains: dict[str, str] = Field(default_factory=dict)
    regions: dict[str, RegionOverride] = Field(default_factory=dict)

    def canonical_hash(self) -> str:
        """SHA-256 of the control's configuration in canonical JSON (Req 1.3)."""
        data: dict[str, Any] = self.model_dump(mode="json")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ConnectorConfig(BaseModel):
    """One source of records for a ledger.

    ``type`` is ``csv``, ``jsonl`` or ``python``. A ``python`` source names a connector class as
    ``entry: "package.module:ClassName"``; the class is constructed with the ledger, the key field,
    the control file's directory and ``options`` as keyword arguments.
    """

    type: str
    path: str | None = None
    entry: str | None = None
    key_field: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class EnricherConfig(BaseModel):
    """A read-only step that adds context to findings after matching.

    ``entry`` names a callable ``package.module:function`` with the signature
    ``(findings, options) -> dict[key, dict[str, str]]``. It may never change a region.
    """

    entry: str
    regions: list[str] = Field(default_factory=lambda: ["OB", "O"])
    options: dict[str, Any] = Field(default_factory=dict)


class LedgerConfig(BaseModel):
    """Per-ledger configuration in a production control file.

    A ledger reads one or more sources. ``connector`` is the single-source shorthand.
    """

    connector: ConnectorConfig | None = None
    sources: list[ConnectorConfig] = Field(default_factory=list)
    key_field: str = ""
    normalisers: list[str] = Field(default_factory=list)

    def all_sources(self) -> list[ConnectorConfig]:
        """Every configured source, the shorthand ``connector`` first."""
        return ([self.connector] if self.connector is not None else []) + list(self.sources)


def region_names(control: ControlConfig) -> dict[str, str]:
    """The display name of every region code for this control (Req 1.4)."""
    return {code: resolve_region(code, control)[0] for code in DEFAULT_REGION_NAMES}


class ControlFile(BaseModel):
    """A production control file with connector configuration per ledger."""

    id: str = ""
    title: str = ""
    app: str = ""
    #: Local, untracked list of keys outside the audited scope (Vampires Req 5).
    exclude_keys_file: str | None = None
    enrichers: list[EnricherConfig] = Field(default_factory=list)
    ledgers: dict[str, LedgerConfig] = Field(default_factory=dict)
    grace_hours: int = 24
    scope: ScopeFilter | None = None
    alias_domains: dict[str, str] = Field(default_factory=dict)
    regions: dict[str, RegionOverride] = Field(default_factory=dict)

    def to_config(self) -> ControlConfig:
        """Extract a ``ControlConfig`` for the matcher and scorer."""
        normalisers = {
            name: ledger_config.normalisers
            for name, ledger_config in self.ledgers.items()
        }
        return ControlConfig(
            normalisers=normalisers,
            grace_hours=self.grace_hours,
            scope=self.scope,
            alias_domains=self.alias_domains,
            regions=self.regions,
        )

    def validate_ledgers(self) -> None:
        """Reject a file that does not declare exactly the three required ledgers (Req 1.1)."""
        required = {"intended", "observed", "billed"}
        actual = set(self.ledgers.keys())
        missing = required - actual
        extra = actual - required
        if missing or extra:
            parts: list[str] = []
            if missing:
                parts.append(f"missing ledgers: {', '.join(sorted(missing))}")
            if extra:
                parts.append(f"extra ledgers: {', '.join(sorted(extra))}")
            raise ValueError("; ".join(parts))

    def validate_normalisers(self) -> None:
        """Reject unknown normaliser names early (Req 1.2)."""
        for ledger_name, ledger_config in self.ledgers.items():
            for norm_name in ledger_config.normalisers:
                try:
                    NormaliserRegistry.get(norm_name)
                except UnknownNormaliserError:
                    raise ValueError(
                        f"Unknown normaliser '{norm_name}' in ledger '{ledger_name}'"
                    ) from None

    def canonical_hash(self) -> str:
        """SHA-256 of the whole control file in canonical JSON: ledgers, sources, rules and wording (Req 1.3)."""
        data: dict[str, Any] = self.model_dump(mode="json")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
