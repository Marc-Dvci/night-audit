"""Normaliser registry and built-in chain normalisers.

Each normaliser has the signature ``(value: str, ctx: dict) -> str``.
The ``ctx`` dict carries control-level parameters such as ``alias_domains``.
Every built-in normaliser is idempotent: applying it twice yields the same
result as applying it once (Req 2.3).
"""

from __future__ import annotations

import re
from typing import Any, Callable

NormaliserFn = Callable[[str, dict[str, Any]], str]

_REGISTRY: dict[str, NormaliserFn] = {}


class UnknownNormaliserError(Exception):
    """Raised when a normaliser name is not in the registry."""


def register(name: str) -> Callable[[NormaliserFn], NormaliserFn]:
    """Decorator that adds a normaliser function to the registry."""

    def decorator(fn: NormaliserFn) -> NormaliserFn:
        _REGISTRY[name] = fn
        return fn

    return decorator


class NormaliserRegistry:
    """Class-level registry of normaliser functions."""

    @staticmethod
    def get(name: str) -> NormaliserFn:
        """Return the normaliser function for *name* or raise."""
        if name not in _REGISTRY:
            raise UnknownNormaliserError(name)
        return _REGISTRY[name]

    @staticmethod
    def names() -> set[str]:
        """Return the set of registered normaliser names."""
        return set(_REGISTRY.keys())


# --- Built-in normalisers ---------------------------------------------------


@register("strip")
def _strip(value: str, ctx: dict[str, Any]) -> str:
    """Strip leading and trailing whitespace."""
    return value.strip()


@register("lower")
def _lower(value: str, ctx: dict[str, Any]) -> str:
    """Lower-case the string."""
    return value.lower()


@register("collapse_whitespace")
def _collapse_whitespace(value: str, ctx: dict[str, Any]) -> str:
    """Replace every run of whitespace with a single space."""
    return re.sub(r"\s+", " ", value)


@register("email_canonical")
def _email_canonical(value: str, ctx: dict[str, Any]) -> str:
    """Canonicalise an email: strip, lower, remove ``+tag``, map alias domains."""
    result = value.strip().lower()
    if "@" not in result:
        return result
    local, domain = result.rsplit("@", 1)
    # Remove the +tag from the local part.
    if "+" in local:
        local = local[: local.index("+")]
    # Map alias domains (e.g. hollowpines.org -> hollowpines.com).
    alias_domains: dict[str, str] = ctx.get("alias_domains", {})
    if domain in alias_domains:
        domain = alias_domains[domain]
    return f"{local}@{domain}"


@register("arn_resource_id")
def _arn_resource_id(value: str, ctx: dict[str, Any]) -> str:
    """Reduce an ARN to its resource id; return non-ARNs unchanged."""
    value = value.strip()
    if not value.startswith("arn:"):
        return value
    parts = value.split(":", maxsplit=5)
    if len(parts) < 6:
        return value
    resource = parts[5]
    if "/" in resource:
        return resource.rsplit("/", 1)[-1]
    if ":" in resource:
        return resource.rsplit(":", 1)[-1]
    return resource


def normalise(raw_key: str, chain: list[str], ctx: dict[str, Any]) -> str:
    """Apply the normaliser *chain* in order to *raw_key* (Req 2.1)."""
    result = raw_key
    for name in chain:
        result = NormaliserRegistry.get(name)(result, ctx)
    return result
