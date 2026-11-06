"""Normaliser registry and built-in chain normalisers.

Each normaliser has the signature ``(value: str, ctx: dict) -> str``.
The ``ctx`` dict carries control-level parameters such as ``alias_domains``.
Every built-in normaliser is idempotent: applying it twice yields the same
result as applying it once (Req 2.3).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

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


def _canonical_domain(domain: str, alias_domains: dict[str, str]) -> str:
    """Map *domain* through the alias table to a domain the table does not map any further.

    Keys and targets are compared stripped and lower-cased, chains (a -> b -> c) are followed to their end, and a
    cycle resolves to its smallest member, so the result is a fixed point (Req 2.3). A target containing ``@`` is not
    a domain and is ignored.
    """
    aliases = {
        k.strip().lower(): t
        for k, v in alias_domains.items()
        if "@" not in (t := v.strip().lower())
    }
    seen: list[str] = []
    while domain in aliases and domain not in seen:
        seen.append(domain)
        domain = aliases[domain]
    if domain in seen:
        return min(seen[seen.index(domain):])
    return domain


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
    return f"{local}@{_canonical_domain(domain, alias_domains)}"


@register("arn_resource_id")
def _arn_resource_id(value: str, ctx: dict[str, Any]) -> str:
    """Reduce an ARN to its resource id; return non-ARNs unchanged (stripped).

    The extracted id is stripped, and an id that is itself an ARN is reduced again, so a second pass is always a
    no-op (Req 2.3). Each step drops the ``arn:`` prefix, so the loop ends.
    """
    value = value.strip()
    while value.startswith("arn:"):
        parts = value.split(":", maxsplit=5)
        if len(parts) < 6:
            break
        resource = parts[5]
        if "/" in resource:
            resource = resource.rsplit("/", 1)[-1]
        elif ":" in resource:
            resource = resource.rsplit(":", 1)[-1]
        value = resource.strip()
    return value


def normalise(raw_key: str, chain: list[str], ctx: dict[str, Any]) -> str:
    """Apply the normaliser *chain* in order to *raw_key* (Req 2.1)."""
    result = raw_key
    for name in chain:
        result = NormaliserRegistry.get(name)(result, ctx)
    return result
