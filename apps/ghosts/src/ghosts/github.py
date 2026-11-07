"""Observed ledger: the members of a GitHub organisation, read with a read-only token (Req 3.2).

Only ``GET /orgs/{org}/members`` is called, through an injected ``HttpClient`` whose one method is ``get``. The token
comes from an environment variable, never from the control. A classic token whose scopes allow writes is refused, and
pagination never follows a link to another host, so the token is only sent to ``api.github.com``.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

from nightaudit.connectors import Connector
from nightaudit.models import LedgerName, Record

from .connectors import read_csv, resolve_path

API_HOST = "api.github.com"
API_VERSION = "2022-11-28"
#: Classic token scopes that only read. Fine-grained tokens send no scope header; give them "Members: read" only.
READ_ONLY_SCOPES: frozenset[str] = frozenset({"read:org", "read:user", "user:email"})
#: GitHub organisation logins: letters, digits and single hyphens, at most 39 characters.
_ORG = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="next"')
MAX_PAGES = 200


@dataclass(frozen=True)
class HttpResponse:
    """What the connector needs from a response. Header names are lower-case."""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


class HttpClient(Protocol):
    """The connector's only way out: GET. No other verb exists on this interface."""

    def get(self, url: str, headers: Mapping[str, str]) -> HttpResponse: ...


class UrllibClient:
    """The default client: ``urllib.request`` with a timeout, HTTPS only."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def get(self, url: str, headers: Mapping[str, str]) -> HttpResponse:
        if urlsplit(url).scheme != "https":
            raise ValueError("GitHub is only read over HTTPS")
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return HttpResponse(response.status, {k.lower(): v for k, v in response.headers.items()},
                                    response.read())
        except urllib.error.HTTPError as exc:
            return HttpResponse(exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read())


class TokenNotReadOnly(PermissionError):
    """The token's scopes allow more than reading."""


def next_link(link_header: str) -> str | None:
    """The ``rel="next"`` URL of a GitHub ``Link`` header, or ``None``."""
    found = _NEXT.search(link_header or "")
    return found.group(1) if found else None


def check_scopes(headers: Mapping[str, str]) -> None:
    """Refuse a classic token with any scope outside ``READ_ONLY_SCOPES``."""
    raw = headers.get("x-oauth-scopes")
    if raw is None:
        return
    scopes = {s.strip() for s in raw.split(",") if s.strip()}
    extra = sorted(scopes - READ_ONLY_SCOPES)
    if extra:
        raise TokenNotReadOnly(f"the GitHub token is not read-only: it has {', '.join(extra)}")


class GitHubMembers(Connector):
    """Observed ledger: one record per organisation member, keyed by the email the roster gives their login."""

    def __init__(
        self,
        ledger: LedgerName,
        org: str,
        roster: str,
        key_field: str = "",
        base_dir: Path | None = None,
        token_env: str = "GITHUB_TOKEN",
        client: HttpClient | None = None,
        environ: Mapping[str, str] | None = None,
        **_: Any,
    ) -> None:
        self._ledger = ledger
        self._org = org
        self._roster = roster
        self._base_dir = base_dir
        self._token_env = token_env
        self._client: HttpClient = client if client is not None else UrllibClient()
        self._environ = environ if environ is not None else os.environ
        #: Every URL requested, in order (all GET).
        self.requested: list[str] = []

    @property
    def ledger(self) -> LedgerName:
        return self._ledger

    @property
    def read_only(self) -> bool:
        return True

    @property
    def source(self) -> str:
        return f"github:{self._org}"

    def _emails_by_login(self) -> dict[str, str]:
        rows = read_csv(resolve_path(self._roster, self._base_dir))
        return {row["github_login"].lower(): row.get("email", "") for row in rows if row.get("github_login")}

    def _members(self) -> list[dict[str, Any]]:
        if not _ORG.match(self._org):
            raise ValueError(f"'{self._org[:60]}' is not a GitHub organisation name")
        token = self._environ.get(self._token_env, "")
        if not token:
            raise PermissionError(f"no GitHub token in ${self._token_env}")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "night-audit-ghosts",
        }
        url: str | None = f"https://{API_HOST}/orgs/{quote(self._org)}/members?per_page=100"
        members: list[dict[str, Any]] = []
        for _ in range(MAX_PAGES):
            if url is None:
                return members
            parts = urlsplit(url)
            if parts.scheme != "https" or parts.hostname != API_HOST:
                raise ValueError("GitHub pagination pointed away from api.github.com; the token was not sent")
            self.requested.append(url)
            response = self._client.get(url, headers)
            if response.status != 200:
                raise RuntimeError(f"GitHub returned HTTP {response.status} for the members of {self._org}")
            check_scopes(response.headers)
            page = json.loads(response.body.decode("utf-8"))
            if not isinstance(page, list):
                raise ValueError("GitHub members response is not a list")
            members.extend(m for m in page if isinstance(m, dict))
            url = next_link(response.headers.get("link", ""))
        raise RuntimeError(f"more than {MAX_PAGES} pages of members")

    def fetch(self) -> list[Record]:
        emails = self._emails_by_login()
        records: list[Record] = []
        for member in self._members():
            login = str(member.get("login", ""))
            if not login:
                continue
            key = emails.get(login.lower()) or f"github:{login}"
            records.append(
                Record(
                    ledger=self._ledger,
                    source=self.source,
                    row_id=f"github:{member.get('id', login)}",
                    raw_key=key,
                    attrs={"system": f"GitHub {self._org}", "status": "member", "login": login},
                )
            )
        return records
