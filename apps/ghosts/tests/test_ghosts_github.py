"""Contract tests: the GitHub organisation members connector replays a recorded response (Req 3.2).

The network edge is stubbed: a replay client answers GET requests from the recorded fixture and records every request.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from ghosts.connectors import HrRoster, IdentityExport, SeatAssignments
from ghosts.github import GitHubMembers, HttpResponse, TokenNotReadOnly, UrllibClient, next_link
from ghosts_testkit import on
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot
from nightaudit.runner import load_control_file

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORDING = json.loads((FIXTURES / "github" / "members.json").read_text("utf-8"))
TOKEN = "github_pat_example_test_token"
ENV = {"GITHUB_TOKEN": TOKEN}


class ReplayClient:
    """Answers GET requests from a recording; anything not recorded is a 404."""

    def __init__(self, pages: list[dict[str, Any]], headers: Mapping[str, str] | None = None) -> None:
        self._pages = {p["url"]: p for p in pages}
        self._extra = dict(headers or {})
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: Mapping[str, str]) -> HttpResponse:
        self.requests.append((url, dict(headers)))
        page = self._pages.get(url)
        if page is None:
            return HttpResponse(404, {}, b'{"message":"Not Found"}')
        return HttpResponse(page["status"], {**page["headers"], **self._extra}, json.dumps(page["body"]).encode())


def connector(client: ReplayClient, org: str = "hollow-pines-demo", environ: Mapping[str, str] = ENV) -> GitHubMembers:
    return GitHubMembers(
        ledger=LedgerName.observed, org=org, roster="hr_roster.csv", base_dir=FIXTURES, client=client, environ=environ
    )


def test_members_are_keyed_by_the_email_the_roster_gives_their_login() -> None:
    client = ReplayClient(RECORDING["pages"])
    records = connector(client).fetch()
    assert [(r.row_id, r.raw_key) for r in records] == [
        ("github:70000001", "b.quill@hollowpines.com"),
        ("github:70000002", "c.wren@hollowpines.com"),  # login case differs from the roster
        ("github:70000003", "github:night-owl-42"),  # nobody on the roster has this login
    ]
    assert records[0].attrs == {"system": "GitHub hollow-pines-demo", "status": "member", "login": "bquill-hp"}
    assert all(r.ledger == LedgerName.observed and r.timestamp is None for r in records)


def test_every_page_is_requested_once_with_get_headers_and_the_token() -> None:
    client = ReplayClient(RECORDING["pages"])
    members = connector(client)
    members.fetch()
    assert members.read_only
    assert [url for url, _ in client.requests] == [p["url"] for p in RECORDING["pages"]]
    for _, headers in client.requests:
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_the_http_interface_has_no_verb_but_get() -> None:
    public = {name for name in dir(UrllibClient) if not name.startswith("_")}
    assert public == {"get"}


def test_a_token_with_write_scopes_is_refused() -> None:
    client = ReplayClient(RECORDING["pages"], headers={"x-oauth-scopes": "read:org, repo, admin:org"})
    with pytest.raises(TokenNotReadOnly, match="admin:org, repo"):
        connector(client).fetch()
    assert len(client.requests) == 1  # stopped at the first response


def test_a_missing_token_stops_before_any_request() -> None:
    client = ReplayClient(RECORDING["pages"])
    with pytest.raises(PermissionError, match="GITHUB_TOKEN"):
        connector(client, environ={}).fetch()
    assert client.requests == []


def test_the_shipped_placeholder_org_stops_before_any_request() -> None:
    client = ReplayClient(RECORDING["pages"])
    with pytest.raises(ValueError, match="not a GitHub organisation name"):
        connector(client, org="<your-org>").fetch()
    assert client.requests == []


def test_pagination_never_sends_the_token_to_another_host() -> None:
    first = dict(RECORDING["pages"][0])
    first["headers"] = {**first["headers"], "link": '<https://collector.invalid/steal?page=2>; rel="next"'}
    client = ReplayClient([first])
    with pytest.raises(ValueError, match="away from api.github.com"):
        connector(client).fetch()
    assert [url for url, _ in client.requests] == [first["url"]]


def test_an_error_status_names_the_status_and_not_the_token() -> None:
    client = ReplayClient([])
    with pytest.raises(RuntimeError) as caught:
        connector(client).fetch()
    assert "HTTP 404" in str(caught.value) and TOKEN not in str(caught.value)


def test_next_link_reads_githubs_link_header() -> None:
    header = RECORDING["pages"][0]["headers"]["link"]
    assert next_link(header) == "https://api.github.com/organizations/90000001/members?per_page=100&page=2"
    assert next_link(RECORDING["pages"][1]["headers"]["link"]) is None


def test_github_is_a_second_observed_source_in_one_run() -> None:
    """With the identity export and GitHub together, a leaver still in the organisation is found by both."""
    control = load_control_file(FIXTURES.parents[1] / "controls" / "staff-access-github.yaml").to_config()
    observed = [
        *IdentityExport(
            ledger=LedgerName.observed, base_dir=FIXTURES, path="identity_export.csv", system="Hollow Pines directory"
        ).fetch(),
        *connector(ReplayClient(RECORDING["pages"])).fetch(),
    ]
    vendors = (("Lantern Chat", "lantern-chat"), ("Crypt Docs", "crypt-docs"), ("Belfry CRM", "belfry-crm"))
    billed = [
        r
        for vendor, name in vendors
        for r in SeatAssignments(
            ledger=LedgerName.billed,
            base_dir=FIXTURES,
            vendor=vendor,
            assignments=f"licences/{name}.csv",
            invoice=f"invoices/{name}.csv",
        ).fetch()
    ]
    intended = on("2026-11-04", HrRoster(ledger=LedgerName.intended, base_dir=FIXTURES, path="hr_roster.csv")).fetch()
    result = match(
        [
            LedgerSnapshot(name=LedgerName.intended, source="hr", records=intended),
            LedgerSnapshot(name=LedgerName.observed, source="identity, github", records=observed),
            LedgerSnapshot(name=LedgerName.billed, source="seats", records=billed),
        ],
        control,
        datetime(2026, 11, 4, 2, 0, tzinfo=UTC),
    )
    assert result.regions["c.wren@hollowpines.com"] == "OB"  # disabled in the directory, still a GitHub member
    assert result.regions["github:night-owl-42"] == "O"
    assert result.regions["b.quill@hollowpines.com"] == "IOB"
    (wren,) = [f for f in result.findings if f.key == "c.wren@hollowpines.com"]
    assert {r.source for r in wren.records if r.ledger == LedgerName.observed} == {"github:hollow-pines-demo"}
