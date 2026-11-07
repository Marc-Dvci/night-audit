"""Record two snapshots of one git commit: the files it tracks and the file paths its specs promise.

    uv run python apps/own-build/snapshot.py [--repo .] [--commit HEAD] [--out apps/own-build/data]

``tracked-files.csv`` has one row per tracked file, ``file,commit``. ``spec-files.csv`` has one row per file, spec and
document that names it, ``file,spec,doc,commit``; the spec documents are read from the same commit with the rules in
``own_build.paths``, which resolve a relative path to the one tracked file it ends, let a folder name every tracked
file under it, and drop build output. Rows are sorted and the files hold no time, so the same commit always gives the
same bytes.

The tracked list is ``git ls-tree -r`` at the commit: the files ``git ls-files`` lists in a clean checkout of it. Reading
the commit and not the index keeps both snapshots to one commit even while other work is staged. Only the read
commands in ``READ_ONLY_GIT`` are ever run (audit rule 3).
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from nightaudit.textfile import write_text_exact

from .paths import promised_files

#: Every git subcommand this module may run. A write command is a defect.
READ_ONLY_GIT: frozenset[str] = frozenset({"rev-parse", "ls-tree", "cat-file"})
SPEC_DOC = re.compile(r"\A\.kiro/specs/([^/]+)/(design|tasks|requirements)\.md\Z")

#: Runs ``git <args>`` in the repository and returns its standard output.
GitRunner = Callable[[list[str]], bytes]


def git_runner(repo: Path) -> GitRunner:
    """The real ``git``, run in *repo*. It refuses any subcommand that is not in ``READ_ONLY_GIT``."""

    def run(args: list[str]) -> bytes:
        if not args or args[0] not in READ_ONLY_GIT:
            raise PermissionError(f"git {args[0] if args else ''} is not a read command")
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
        return done.stdout

    return run


def resolve_commit(git: GitRunner, rev: str) -> str:
    """The full object name of the commit *rev* names."""
    return git(["rev-parse", "--verify", f"{rev}^{{commit}}"]).decode("utf-8").strip()


def tracked_files(git: GitRunner, commit: str) -> list[str]:
    """The paths of every file in the commit's tree, sorted."""
    out = git(["ls-tree", "-r", "-z", "--full-tree", "--name-only", commit])
    return sorted(p for p in out.decode("utf-8").split("\0") if p)


def spec_rows(git: GitRunner, commit: str, tracked: list[str]) -> list[tuple[str, str, str]]:
    """``(file, spec, doc)`` for every tracked file, or path as written, that a spec document at the commit promises.

    The spans are resolved against *tracked* with the rules in ``own_build.paths``.
    """
    tracked_set = frozenset(tracked)
    rows: set[tuple[str, str, str]] = set()
    for path in tracked:
        found = SPEC_DOC.match(path)
        if found is None:
            continue
        text = git(["cat-file", "blob", f"{commit}:{path}"]).decode("utf-8")
        for file in promised_files(text, found.group(1), tracked_set):
            rows.add((file, found.group(1), f"{found.group(2)}.md"))
    return sorted(rows)


def csv_text(header: list[str], rows: list[list[str]]) -> str:
    """CSV with ``\\n`` line endings, whatever the platform."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def record(git: GitRunner, rev: str, out: Path) -> str:
    """Write ``tracked-files.csv`` and ``spec-files.csv`` for *rev* into *out*; return the commit."""
    commit = resolve_commit(git, rev)
    tracked = tracked_files(git, commit)
    out.mkdir(parents=True, exist_ok=True)
    write_text_exact(out / "tracked-files.csv", csv_text(["file", "commit"], [[p, commit] for p in tracked]))
    specs = spec_rows(git, commit, tracked)
    write_text_exact(
        out / "spec-files.csv", csv_text(["file", "spec", "doc", "commit"], [[f, s, d, commit] for f, s, d in specs])
    )
    return commit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="the repository (default: the current folder)")
    parser.add_argument("--commit", default="HEAD", help="the commit to record (default: HEAD)")
    parser.add_argument("--out", default=None, help="where to write (default: <repo>/apps/own-build/data)")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    out = Path(args.out) if args.out else repo / "apps" / "own-build" / "data"
    commit = record(git_runner(repo), args.commit, out)
    print(f"recorded commit {commit} into {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
