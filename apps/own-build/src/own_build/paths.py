"""Repository file paths: one canonical spelling, the rule for which backticked spans in a spec name a file or a folder,
and the rule for which tracked files a span intends.

All functions are pure. ``canonical_path`` is idempotent (audit rule 6), so the same input always gives the same key.

Reading a spec (``spec_paths``, ``spec_folders``). The rule for "plainly names a file" was fixed before any data was
read. A span is a file when it is:

* written in single backticks, outside a fenced code block;
* the whole span, with no space, quote, bracket, brace, colon, ``#``, ``*``, ``?``, ``<`` or ``>`` in it;
* made of ``/``-separated segments of letters, digits, ``.``, ``_`` and ``-``, with at least one ``/``;
* ending in a segment whose last dot is followed by a letter-led extension.

A span is a folder when it is the same kind of path and ends in ``/`` (``apps/ghosts/``). A glob, a template
(``runs/<id>/x.json``), a bare name (``report.py``), a dotted identifier (``ghosts.review``), a URL route and a command
are neither. Reading a spec never looks at the repository.

Resolving a span (``promised_files``). The first recorded night showed that the reading rule alone overstates: 24 of its
32 "promised and never built" files were paths written relative to a folder, or folders. So the snapshot, which is the
one step that holds both the specs and the tracked list of one commit, resolves each span with these rules:

1. A file span that is a tracked file names that file.
2. Otherwise, a file span that is a suffix of exactly one tracked path, at a ``/`` boundary, names that path
   (``tests/test_x.py`` names ``skeleton/tests/test_x.py`` when no other tracked path ends in ``/tests/test_x.py``).
3. Otherwise the span stays as written: with no match, or with two or more, it names no single file, and it lands on
   the list of files promised and never built.
4. A folder span intends every tracked file under it. A folder that holds no tracked file intends nothing.
5. A span is not a repository promise, and is dropped, when it has a ``node_modules`` or ``dist`` segment (build
   output) or is listed in ``NOT_PROMISES`` (files a spec says a tool writes into somebody else's project).

The three ledgers stay independent in a run: the control reads three recorded files, and this resolution happens once,
when the snapshot is taken.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator

_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
_EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]*\Z")
_SPAN = re.compile(r"`([^`\n]+)`")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

#: A path with one of these segments is build output or installed packages, not something a repository promises.
BUILD_OUTPUT_SEGMENTS: frozenset[str] = frozenset({"node_modules", "dist"})

#: Files a spec names that a tool writes into the user's own project, so they are not files of this repository.
#: The night-shift design (the Kiro power) lists them as the steps of ``add-control``. Keyed by spec folder name.
NOT_PROMISES: dict[str, frozenset[str]] = {
    "night-shift": frozenset({"tests/test_contracts.py", "tests/test_casebook.py"}),
}


def canonical_path(value: str) -> str:
    """A repository path in one spelling: stripped, ``/`` separators, no leading ``./``.

    Applying it twice gives the same result as applying it once. An empty string stays empty.
    """
    text = value.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _clean_segments(segments: list[str]) -> bool:
    return all(s not in ("", ".", "..") and _SEGMENT.fullmatch(s) is not None for s in segments)


def file_path_in(span: str) -> str | None:
    """The repository path a backticked *span* plainly names, or ``None`` when it does not name a file."""
    if span != span.strip():
        return None
    text = canonical_path(span)
    if not text or text.startswith("/") or "/" not in text:
        return None
    segments = text.split("/")
    if not _clean_segments(segments) or _EXTENSION.search(segments[-1]) is None:
        return None
    return text


def folder_in(span: str) -> str | None:
    """The folder a backticked *span* plainly names, written with its closing ``/``, or ``None``."""
    if span != span.strip():
        return None
    text = canonical_path(span)
    if not text.endswith("/") or text.startswith("/"):
        return None
    if not _clean_segments(text[:-1].split("/")):
        return None
    return text


def _spans(markdown: str) -> Iterator[str]:
    """Every backticked span of a markdown text, outside fenced blocks, in order."""
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
            yield span.group(1)


def spec_paths(markdown: str) -> list[str]:
    """Every file path a spec's markdown names in backticks, outside fenced blocks, sorted and without repeats."""
    found = {path for span in _spans(markdown) if (path := file_path_in(span)) is not None}
    return sorted(found)


def spec_folders(markdown: str) -> list[str]:
    """Every folder a spec's markdown names in backticks, outside fenced blocks, sorted and without repeats."""
    found = {folder for span in _spans(markdown) if (folder := folder_in(span)) is not None}
    return sorted(found)


def is_build_output(path: str) -> bool:
    """Whether the path runs through build output or installed packages (``dist``, ``node_modules``)."""
    return any(segment in BUILD_OUTPUT_SEGMENTS for segment in path.split("/"))


def resolve_file(span: str, tracked: Collection[str]) -> str:
    """The tracked file a file span names (rules 1 to 3): the file itself, its one suffix match, or the span as written."""
    if span in tracked:
        return span
    matches = [path for path in tracked if path.endswith("/" + span)]
    return matches[0] if len(matches) == 1 else span


def files_under(folder: str, tracked: Iterable[str]) -> list[str]:
    """Every tracked file under a folder span (rule 4)."""
    return [path for path in tracked if path.startswith(folder)]


def promised_files(markdown: str, spec: str, tracked: Collection[str]) -> list[str]:
    """The files one spec document promises, given the files git tracks: sorted and without repeats.

    *spec* is the spec's folder name under ``.kiro/specs``; it selects the ``NOT_PROMISES`` entry.
    """
    ignored = NOT_PROMISES.get(spec, frozenset())
    found: set[str] = set()
    for path in spec_paths(markdown):
        if not is_build_output(path) and path not in ignored:
            found.add(resolve_file(path, tracked))
    for folder in spec_folders(markdown):
        if not is_build_output(folder):
            found.update(files_under(folder, tracked))
    return sorted(found)
