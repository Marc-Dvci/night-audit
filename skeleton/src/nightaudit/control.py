"""Control file schema, loading, validation, and canonical hash.

A control file declares three ledgers, their key fields and normalisers, the
grace window, scope filters, and optional region overrides.  ``ControlConfig``
is the subset the matcher needs; ``ControlFile`` adds connector configuration.
"""

from __future__ import annotations

import hashlib
import json
import string
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import (
    DEFAULT_REGION_MEANINGS,
    DEFAULT_REGION_NAMES,
    DEFAULT_REGION_SEVERITIES,
    FINDING_REGIONS,
    ColumnUi,
    DownloadUi,
    HeadlineUi,
    LedgerUi,
    NounUi,
    UiConfig,
    UnkeyedUi,
)
from .normalisers import NormaliserRegistry, UnknownNormaliserError

#: The slots a control author may use in a headline template (Req 1.1).
HEADLINE_SLOTS: frozenset[str] = frozenset({"count", "amount", "noun"})


def _check_template(template: str) -> None:
    parsed = list(string.Formatter().parse(template))
    fields = {name for _, name, _, _ in parsed if name is not None}
    unknown = fields - HEADLINE_SLOTS
    if unknown:
        raise ValueError(f"headline template uses unknown slots: {', '.join(sorted(unknown))}")
    if "count" not in fields:
        raise ValueError("headline template must contain {count}")
    # Every number in a headline comes from the run (audit rule 2), so the fixed words may not hold digits.
    if any(ch.isdigit() for literal, _, _, _ in parsed for ch in literal):
        raise ValueError("headline template text may not contain digits; numbers come from the run")


class UiSection(BaseModel):
    """The optional ``ui`` section of a control file, as written. ``resolve_ui`` fills the gaps (Req 1.1, 1.2)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    tagline: str | None = None
    noun: NounUi | None = None
    ledgers: dict[str, LedgerUi] = Field(default_factory=dict)
    columns: list[ColumnUi] = Field(default_factory=list)
    headlines: dict[str, HeadlineUi] = Field(default_factory=dict)
    #: The words for billed lines with no key (Req 10.4). Absent means the wording used before this field existed.
    unkeyed: UnkeyedUi | None = None
    #: Files beside the run that the page links to (Req 10.6).
    downloads: list[DownloadUi] = Field(default_factory=list)

    @field_validator("headlines", mode="before")
    @classmethod
    def _plain_string_is_both_forms(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: ({"one": v, "other": v} if isinstance(v, str) else v) for k, v in value.items()}
        return value

    @model_validator(mode="after")
    def _validate(self) -> UiSection:
        unknown_ledgers = set(self.ledgers) - {"intended", "observed", "billed"}
        if unknown_ledgers:
            raise ValueError(f"ui.ledgers names unknown ledgers: {', '.join(sorted(unknown_ledgers))}")
        for code, headline in self.headlines.items():
            if code not in FINDING_REGIONS:
                raise ValueError(f"ui.headlines names '{code}', which is not a finding region")
            _check_template(headline.one)
            _check_template(headline.other)
        return self


def resolve_region(code: str, control: ControlConfig) -> tuple[str, str, str]:
    """Resolve ``(name, severity, meaning)`` from overrides or defaults (Req 1.4).

    Shared by the matcher, the state module and the explainer so the resolution
    rule lives in one place.
    """
    override = control.regions.get(code)
    if override is not None:
        name = override.name if override.name is not None else DEFAULT_REGION_NAMES[code]
        severity = override.severity if override.severity is not None else DEFAULT_REGION_SEVERITIES[code]
        meaning = override.meaning if override.meaning is not None else DEFAULT_REGION_MEANINGS[code]
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


class SummariserConfig(BaseModel):
    """A read-only step that adds sentences to the run after matching (Req 10.2).

    ``entry`` names a callable ``package.module:function`` with the signature ``(result, options) -> list[str]``, and
    optionally a keyword parameter ``control``. Every number in a sentence must appear in the run's evidence rows.
    """

    model_config = ConfigDict(extra="forbid")

    entry: str
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


def region_meanings(control: ControlConfig) -> dict[str, str]:
    """The one-sentence meaning of every region code for this control (Req 1.4, ui-kit Req 2.6)."""
    return {code: resolve_region(code, control)[2] for code in DEFAULT_REGION_NAMES}


#: Default headline sentences per finding region (ui-kit design §3). ``{name}`` is the region's resolved name and is
#: filled in by ``resolve_ui``; control authors only get ``{count}``, ``{amount}`` and ``{noun}``.
DEFAULT_HEADLINES: dict[str, tuple[str, str]] = {
    "OB": (
        "{count} {name} exists and is on the bill with no approval: {amount}.",
        "{count} {name}s exist and are on the bill with no approval: {amount}.",
    ),
    "B": (
        "{count} {name} is on the bill for something nobody approved or can see: {amount}.",
        "{count} {name}s are on the bill for something nobody approved or can see: {amount}.",
    ),
    "IB": (
        "{count} {name} is approved and billed but cannot be seen: {amount}.",
        "{count} {name}s are approved and billed but cannot be seen: {amount}.",
    ),
    "I": (
        "{count} {name} is approved but gone and unbilled.",
        "{count} {name}s are approved but gone and unbilled.",
    ),
    "O": (
        "{count} {name} exists with no approval and costs nothing.",
        "{count} {name}s exist with no approval and cost nothing.",
    ),
}


def fill_region_name(template: str, name: str) -> str:
    """Put a region's resolved name into a default template; braces in the name stay literal text."""
    safe = name.replace("{", "{{").replace("}", "}}")
    return template.replace("{name}", safe)


def resolve_ui(control: ControlFile) -> UiConfig:
    """The words a run renders with: the ``ui`` section with every gap filled by a neutral default (Req 1.2)."""
    section = control.ui if control.ui is not None else UiSection()
    config = control.to_config()
    headlines: dict[str, HeadlineUi] = {}
    for code, (one, other) in DEFAULT_HEADLINES.items():
        name = resolve_region(code, config)[0]
        headlines[code] = section.headlines.get(code) or HeadlineUi(
            one=fill_region_name(one, name), other=fill_region_name(other, name)
        )
    defaults = UiConfig()
    ledgers = dict(defaults.ledgers)
    ledgers.update(section.ledgers)
    return UiConfig(
        title=section.title or control.title or control.id or defaults.title,
        tagline=section.tagline or defaults.tagline,
        noun=section.noun or defaults.noun,
        ledgers=ledgers,
        columns=list(section.columns) if section.columns else list(defaults.columns),
        headlines=headlines,
        unkeyed=section.unkeyed or defaults.unkeyed,
        downloads=list(section.downloads),
    )


class ControlFile(BaseModel):
    """A production control file with connector configuration per ledger."""

    id: str = ""
    title: str = ""
    app: str = ""
    #: Local, untracked list of keys outside the audited scope (Vampires Req 5).
    exclude_keys_file: str | None = None
    #: Local, untracked list of the keys and name prefixes this deployment audits. Absent means everything.
    include_keys_file: str | None = None
    enrichers: list[EnricherConfig] = Field(default_factory=list)
    #: Steps that add sentences to the run (Req 10.2). Part of the canonical hash when present.
    summarisers: list[SummariserConfig] = Field(default_factory=list)
    ledgers: dict[str, LedgerConfig] = Field(default_factory=dict)
    grace_hours: int = 24
    scope: ScopeFilter | None = None
    alias_domains: dict[str, str] = Field(default_factory=dict)
    regions: dict[str, RegionOverride] = Field(default_factory=dict)
    #: The words the UI and the morning report use (ui-kit Req 1). Part of the canonical hash.
    ui: UiSection | None = None

    def to_config(self) -> ControlConfig:
        """Extract a ``ControlConfig`` for the matcher and scorer."""
        normalisers = {name: ledger_config.normalisers for name, ledger_config in self.ledgers.items()}
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
                    raise ValueError(f"Unknown normaliser '{norm_name}' in ledger '{ledger_name}'") from None

    def canonical_hash(self) -> str:
        """SHA-256 of the whole control file in canonical JSON: ledgers, sources, rules and wording (Req 1.3).

        A control without a ``ui`` section hashes as it did before the section existed, so its run ids do not change.
        The same holds for the fields added by Req 10 (``summarisers``, ``ui.unkeyed``, ``ui.downloads``) while they
        are empty.
        """
        data: dict[str, Any] = self.model_dump(mode="json")
        if data.get("ui") is None:
            data.pop("ui", None)
        else:
            if data["ui"].get("unkeyed") is None:
                data["ui"].pop("unkeyed", None)
            if not data["ui"].get("downloads"):
                data["ui"].pop("downloads", None)
        if not data.get("summarisers"):
            data.pop("summarisers", None)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
