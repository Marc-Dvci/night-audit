"""P4: every built-in normaliser is idempotent (Req 2.3)."""

from __future__ import annotations

import pytest
from hostile import DOMAINS, alias_maps, raw_keys
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.normalisers import NormaliserRegistry


@st.composite
def values_and_aliases(draw: st.DrawFn) -> tuple[str, dict[str, str]]:
    """Any string, or an email whose domain is one of the alias domains (as key or target), with any tag and case."""
    aliases = draw(alias_maps())
    domains = sorted(set(DOMAINS) | set(aliases) | set(aliases.values()))
    domain = st.sampled_from(domains)
    if aliases:
        domain = st.one_of(st.sampled_from(sorted(aliases)), domain)
    email = st.builds(
        lambda local, tag, domain: f"{local}{tag}@{domain}",
        st.one_of(st.sampled_from(["li.wei", "J.Marsh", "a@b", ""]), st.text(max_size=6)),
        st.one_of(st.just(""), st.text(max_size=4).map(lambda t: "+" + t)),
        st.one_of(domain, domain.map(str.upper)),
    )
    return draw(st.one_of(raw_keys(), st.text(), email, email)), aliases


@pytest.mark.property
@given(name=st.sampled_from(sorted(NormaliserRegistry.names())), case=values_and_aliases())
def test_property_applying_a_normaliser_twice_equals_applying_it_once(
    name: str, case: tuple[str, dict[str, str]]
) -> None:
    """P4 (Req 2.3): "For any string s and any registered normaliser n, n(n(s, ctx), ctx) == n(s, ctx)."

    ``ctx`` carries ``alias_domains`` exactly as a control file supplies it: mixed case, padding, chains and cycles.
    """
    value, alias_domains = case
    normaliser = NormaliserRegistry.get(name)
    ctx = {"alias_domains": alias_domains}
    once = normaliser(value, ctx)
    assert normaliser(once, ctx) == once


def test_regression_arn_resource_id_strips_the_resource_id_it_extracts() -> None:
    """Shrunk from P4: the resource part came back as ``"\\xa0i-0aa1"`` and only a second pass stripped it."""
    arn = NormaliserRegistry.get("arn_resource_id")
    assert arn("arn:aws:ec2:us-east-1:111122223333:instance/\xa0i-0aa1", {}) == "i-0aa1"


def test_regression_arn_resource_id_reduces_an_arn_left_inside_a_resource_id() -> None:
    """Found while fixing the case above, not by Hypothesis: one pass left an ARN that a second pass reduced."""
    arn = NormaliserRegistry.get("arn_resource_id")
    once = arn("arn:aws:iam::111122223333:user/arn:aws:s3:::lab-logs-bucket", {})
    assert once == "lab-logs-bucket"
    assert arn(once, {}) == once


def test_regression_email_canonical_writes_the_alias_target_in_canonical_form() -> None:
    """Shrunk from P4: the target ``" example.net "`` was copied as written and only a second pass stripped it."""
    email = NormaliserRegistry.get("email_canonical")
    assert email("@HOLLOWPINES.ORG", {"alias_domains": {"hollowpines.org": " example.net "}}) == "@example.net"


def test_regression_email_canonical_follows_alias_chains_and_cycles_to_a_fixed_point() -> None:
    """Found while fixing the case above, not by Hypothesis: a chain or cycle moved the domain again on each pass."""
    email = NormaliserRegistry.get("email_canonical")
    chain = {"alias_domains": {"a.org": "b.org", "B.ORG": "c.com"}}
    cycle = {"alias_domains": {"a.org": "b.org", "b.org": "a.org"}}
    assert email("X+tag@A.org", chain) == "x@c.com"
    assert email("x@b.org", cycle) == email("x@a.org", cycle) == "x@a.org"
    assert email(email("x@b.org", cycle), cycle) == "x@a.org"
