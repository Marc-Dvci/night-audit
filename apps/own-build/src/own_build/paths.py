"""Repository file paths: one canonical spelling, and the rule for which backticked spans in a spec name a file.

Both functions are pure. ``canonical_path`` is idempotent (audit rule 6), so the same input always gives the same key.

The rule for "plainly names a file" was fixed before any data was read. A span is a promise when it is:

* written in single backticks, outside a fenced code block;
* the whole span, with no space, quote, bracket, brace, colon, ``#``, ``*``, ``?``, ``<`` or ``>`` in it;
* made of ``/``-separated segments of letters, digits, ``.``, ``_`` and ``-``, with at least one ``/``;
* ending in a segment whose last dot is followed by a letter-led extension.

So a directory (``lean/``), a glob, a template (``runs/<id>/x.json``), a bare name (``report.py``), a dotted identifier
(``ghosts.review``), a URL route and a command are not files. A bare name is left out on purpose: it names no
location, and a path written relative to some other folder cannot be told from a repository path by reading the spec
alone. The parser never looks at the repository to decide; the three ledgers stay independent.
"""

from __future__ import annotations

import re

_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
_EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]*\Z")
_SPAN = re.compile(r"`([^`\n]+)`")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def canonical_path(value: str) -> str:
    """A repository path in one spelling: stripped, ``/`` separators, no leading ``./``.

    Applying it twice gives the same result as applying it once. An empty string stays empty.
    """
    text = value.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def file_path_in(span: str) -> str | None:
    """The repository path a backticked *span* plainly names, or ``None`` when it does not name a file."""
    if span != span.strip():
        return None
    text = canonical_path(span)
    if not text or text.startswith("/") or "/" not in text:
        return None
    segments = text.split("/")
    if any(s in ("", ".", "..") or not _SEGMENT.fullmatch(s) for s in segments):
        return None
    if _EXTENSION.search(segments[-1]) is None:
        return None
    return text


def spec_paths(markdown: str) -> list[str]:
    """Every file path a spec's markdown names in backticks, outside fenced blocks, sorted and without repeats."""
    found: set[str] = set()
    fence: str | None = None
    for line in markdown.splitlines():
        marker = _FENCE.match(line)
        if marker is not None:
            mark = marker.group(1)
            if fence is None:
                fence = mark[0]
                continue
            if mark[0] == fence:
                fence = None
                continue
        if fence is not None:
            continue
        for span in _SPAN.finditer(line):
            path = file_path_in(span.group(1))
            if path is not None:
                found.add(path)
    return sorted(found)
