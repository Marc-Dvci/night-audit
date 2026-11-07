"""The snapshot script: deterministic, tied to one commit, and read-only on git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from own_build.snapshot import READ_ONLY_GIT, GitRunner, git_runner, main, record, resolve_commit, tracked_files

COMMIT = "a" * 40

README = "# Repo\n"
DESIGN = "The matcher is `src/match.py`. Directory `src/`. Glob `docs/*.md`. Bare `README.md`.\n"
TASKS = "- [x] 1. Write `src/match.py` and `deploy/stack.yaml`.\n```text\n`not/promised.py`\n```\n"
OTHER = "Not a spec document: `src/ignored.py`.\n"
TREE = {
    ".kiro/specs/alpha/design.md": DESIGN,
    ".kiro/specs/alpha/tasks.md": TASKS,
    ".kiro/specs/alpha/notes.md": OTHER,
    ".kiro/steering/product.md": OTHER,
    "src/match.py": "",
    "README.md": README,
}


class StubGit:
    """The git edge: a commit holding ``TREE``. It records every command it was asked to run."""

    def __init__(self, tree: dict[str, str]) -> None:
        self.tree = tree
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> bytes:
        self.calls.append(args)
        if args[0] == "rev-parse":
            return f"{COMMIT}\n".encode()
        if args[0] == "ls-tree":
            assert args[-1] == COMMIT
            return b"".join(p.encode() + b"\0" for p in self.tree)
        if args[0] == "cat-file":
            commit, _, path = args[2].partition(":")
            assert commit == COMMIT
            return self.tree[path].encode()
        raise AssertionError(args)


def test_the_tracked_files_are_sorted_and_all_name_the_commit(tmp_path: Path) -> None:
    git = StubGit(TREE)
    assert record(git, "HEAD", tmp_path) == COMMIT
    lines = (tmp_path / "tracked-files.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "file,commit"
    assert [line.split(",")[0] for line in lines[1:]] == sorted(TREE)
    assert all(line.endswith(f",{COMMIT}") for line in lines[1:])


def test_the_promises_come_from_the_design_tasks_and_requirements_documents_only(tmp_path: Path) -> None:
    record(StubGit(TREE), "HEAD", tmp_path)
    assert (tmp_path / "spec-files.csv").read_text(encoding="utf-8").splitlines() == [
        "file,spec,doc,commit",
        f"deploy/stack.yaml,alpha,tasks.md,{COMMIT}",
        f"src/match.py,alpha,design.md,{COMMIT}",
        f"src/match.py,alpha,tasks.md,{COMMIT}",
    ]


def test_the_files_are_written_with_unix_line_endings_whatever_the_platform(tmp_path: Path) -> None:
    record(StubGit(TREE), "HEAD", tmp_path)
    for name in ("tracked-files.csv", "spec-files.csv"):
        data = (tmp_path / name).read_bytes()
        assert b"\r" not in data and data.endswith(b"\n")


def test_a_second_snapshot_of_the_same_commit_has_the_same_bytes(tmp_path: Path) -> None:
    record(StubGit(TREE), "HEAD", tmp_path / "one")
    record(StubGit(dict(reversed(TREE.items()))), "HEAD", tmp_path / "two")
    for name in ("tracked-files.csv", "spec-files.csv"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_every_command_the_snapshot_runs_is_a_read_command(tmp_path: Path) -> None:
    git = StubGit(TREE)
    record(git, "HEAD", tmp_path)
    assert git.calls and {call[0] for call in git.calls} <= READ_ONLY_GIT


@pytest.mark.parametrize("verb", ["commit", "add", "checkout", "reset", "push", "config", "clean", "gc"])
def test_the_real_git_runner_refuses_a_command_that_could_write(verb: str, tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        git_runner(tmp_path)([verb, "x"])


def real_repo(tmp_path: Path) -> tuple[Path, GitRunner]:
    """A throwaway repository made with the real git, under the test's own folder. No user config is touched."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def sh(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", *args],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    sh("init", "-q")
    for path, text in TREE.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode())
    sh("add", "-A")
    sh("commit", "-q", "-m", "fixture")
    return repo, git_runner(repo)


def test_a_relative_path_a_folder_and_build_output_are_resolved_against_the_commit_they_are_read_from(
    tmp_path: Path,
) -> None:
    tree = {
        ".kiro/specs/beta/design.md": (
            "Tests in `tests/test_x.py`. Folder `lib/`. Output `web/dist/app.js`. Stale `old/gone.py`. Twice `u/h.py`.\n"
        ),
        "skeleton/tests/test_x.py": "",
        "lib/a.py": "",
        "lib/sub/b.py": "",
        "web/dist/app.js": "",
        "p/u/h.py": "",
        "q/u/h.py": "",
    }
    record(StubGit(tree), "HEAD", tmp_path)
    assert (tmp_path / "spec-files.csv").read_text(encoding="utf-8").splitlines() == [
        "file,spec,doc,commit",
        f"lib/a.py,beta,design.md,{COMMIT}",
        f"lib/sub/b.py,beta,design.md,{COMMIT}",
        f"old/gone.py,beta,design.md,{COMMIT}",
        f"skeleton/tests/test_x.py,beta,design.md,{COMMIT}",
        f"u/h.py,beta,design.md,{COMMIT}",
    ]


def test_the_real_git_lists_the_same_files_as_the_tree_it_committed(tmp_path: Path) -> None:
    repo, git = real_repo(tmp_path)
    commit = resolve_commit(git, "HEAD")
    assert len(commit) == 40
    assert tracked_files(git, commit) == sorted(TREE)
    assert tracked_files(git, "HEAD") == sorted(TREE)
    # Staged and untracked work does not enter a snapshot of the commit.
    (repo / "untracked.py").write_text("x = 1\n", encoding="utf-8")
    assert "untracked.py" not in tracked_files(git, commit)


def test_the_command_line_records_a_real_repository_twice_with_the_same_bytes(tmp_path: Path) -> None:
    repo, _ = real_repo(tmp_path)
    for name in ("one", "two"):
        assert main(["--repo", str(repo), "--out", str(tmp_path / name)]) == 0
    for name in ("tracked-files.csv", "spec-files.csv"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    assert "src/match.py,alpha,design.md," in (tmp_path / "one" / "spec-files.csv").read_text(encoding="utf-8")
