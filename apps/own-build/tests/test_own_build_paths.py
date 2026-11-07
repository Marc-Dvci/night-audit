"""Which backticked spans in a spec name a file, and one spelling for a repository path (audit rule 6).

The parser cases are in the casebook, written before the parser. The properties hold for any text.
"""

from __future__ import annotations

import random
from typing import Any

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st
from own_build.paths import (
    canonical_path,
    file_path_in,
    folder_in,
    is_build_output,
    promised_files,
    spec_folders,
    spec_paths,
)
from own_build_testkit import CASEBOOK

CASEBOOK_DATA: dict[str, list[dict[str, Any]]] = yaml.safe_load(CASEBOOK.read_text(encoding="utf-8"))
CASES = CASEBOOK_DATA["parser"]
FOLDER_CASES = CASEBOOK_DATA["folders"]
RESOLVE_CASES = CASEBOOK_DATA["resolve"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_the_parser_reads_exactly_the_files_the_casebook_says_a_text_names(case: dict[str, Any]) -> None:
    assert spec_paths(case["text"]) == sorted(case["expect"])


@pytest.mark.parametrize("case", FOLDER_CASES, ids=[c["id"] for c in FOLDER_CASES])
def test_the_parser_reads_exactly_the_folders_the_casebook_says_a_text_names(case: dict[str, Any]) -> None:
    assert spec_folders(case["text"]) == sorted(case["expect"])


@pytest.mark.parametrize("case", RESOLVE_CASES, ids=[c["id"] for c in RESOLVE_CASES])
def test_a_spec_promises_exactly_the_files_the_casebook_says_given_the_tracked_files(case: dict[str, Any]) -> None:
    assert promised_files(case["text"], case["spec"], frozenset(case["tracked"])) == sorted(case["expect"])


def test_a_folder_is_not_a_file_and_a_file_is_not_a_folder() -> None:
    assert file_path_in("apps/ghosts/") is None
    assert folder_in("apps/ghosts/") == "apps/ghosts/"
    assert folder_in("apps/ghosts/app.py") is None
    assert folder_in("apps/ghosts") is None


@pytest.mark.parametrize(
    ("path", "output"),
    [
        ("skeleton/web/dist/index.html", True),
        ("skeleton/web/node_modules/axe-core/axe.min.js", True),
        ("dist/", True),
        ("skeleton/web/src/distance.ts", False),
        ("skeleton/web/dist-notes/a.md", False),
        ("apps/ghosts/app.py", False),
    ],
)
def test_only_a_dist_or_node_modules_segment_makes_a_path_build_output(path: str, output: bool) -> None:
    assert is_build_output(path) is output


def test_a_bare_name_is_not_a_file_because_it_names_no_location() -> None:
    assert file_path_in("pyproject.toml") is None
    assert file_path_in("skeleton/pyproject.toml") == "skeleton/pyproject.toml"


def test_a_dotfile_in_a_directory_is_a_file() -> None:
    assert file_path_in(".github/workflows/ci.yml") == ".github/workflows/ci.yml"
    assert file_path_in("docs/.gitignore") == "docs/.gitignore"


def test_a_directory_with_a_dot_in_its_name_is_not_a_file() -> None:
    assert file_path_in("api.github.com/orgs") is None
    assert file_path_in("v1.2/") is None


def test_backslashes_and_a_leading_dot_slash_give_the_repository_spelling() -> None:
    assert canonical_path(".\\src\\a.py") == "src/a.py"
    assert canonical_path("./src/a.py") == "src/a.py"
    assert canonical_path("  src/a.py ") == "src/a.py"
    assert canonical_path("") == ""


@pytest.mark.property
@given(value=st.text(max_size=60))
def test_property_a_canonical_path_is_a_fixed_point(value: str) -> None:
    """Audit rule 6: for any string s, canonical_path(canonical_path(s)) == canonical_path(s)."""
    once = canonical_path(value)
    assert canonical_path(once) == once


PATH_ALPHABET = st.sampled_from(list("ab./\\-_ `*<>{}:#?0"))


@pytest.mark.property
@given(text=st.text(alphabet=PATH_ALPHABET, max_size=40))
def test_property_a_span_that_names_a_file_names_it_in_one_spelling(text: str) -> None:
    """For any span s, file_path_in(s) is None or a canonical path with a directory and an extension."""
    found = file_path_in(text)
    if found is not None:
        assert canonical_path(found) == found
        assert "/" in found and not found.startswith("/") and "\\" not in found
        assert all(s not in ("", ".", "..") for s in found.split("/"))
        assert file_path_in(found) == found


@pytest.mark.property
@given(
    paths=st.lists(
        st.from_regex(r"[a-z]{1,4}(/[a-z]{1,4}){0,2}/[a-z]{1,4}\.[a-z]{1,3}", fullmatch=True), min_size=0, max_size=8
    ),
    prose=st.text(alphabet="abc .,\n", max_size=30),
)
def test_property_the_promises_do_not_depend_on_order_or_repeats(paths: list[str], prose: str) -> None:
    """For any list of file paths written in backticks among prose, the parser reads back the set of them."""
    forward = " ".join(f"{prose} `{p}`" for p in paths)
    backward = " ".join(f"{prose} `{p}` `{p}`" for p in reversed(paths))
    assert spec_paths(forward) == sorted(set(paths)) == spec_paths(backward)


@pytest.mark.property
@given(inner=st.lists(st.sampled_from(["a/b.py", "`c/d.py`", "plain", "x/y.md"]), max_size=6))
def test_property_a_fenced_block_never_adds_a_promise(inner: list[str]) -> None:
    """For any lines placed inside a fence, the promises are those of the text without the fence."""
    fenced = "intro `keep/me.py`\n```text\n" + "\n".join(inner) + "\n```\nend\n"
    assert spec_paths(fenced) == ["keep/me.py"]


TRACKED = st.sets(st.from_regex(r"[a-c]{1,2}(/[a-c]{1,2}){0,2}/[a-c]{1,2}\.[a-z]{1,2}", fullmatch=True), max_size=10)
SPANS = st.lists(
    st.one_of(
        st.from_regex(r"[a-c]{1,2}(/[a-c]{1,2}){0,2}/[a-c]{1,2}\.[a-z]{1,2}", fullmatch=True),
        st.from_regex(r"[a-c]{1,2}(/[a-c]{1,2}){0,2}/", fullmatch=True),
    ),
    max_size=6,
)


@pytest.mark.property
@given(tracked=TRACKED, spans=SPANS)
def test_property_a_promise_is_a_tracked_file_or_a_path_a_spec_wrote(tracked: set[str], spans: list[str]) -> None:
    """For any tracked files and any spans, every promised path is tracked or is a file span written as it is."""
    text = " ".join(f"`{s}`" for s in spans)
    written = set(spec_paths(text))
    assert set(promised_files(text, "alpha", tracked)) <= tracked | written


@pytest.mark.property
@given(tracked=TRACKED, spans=SPANS)
def test_property_a_tracked_file_a_spec_names_as_it_is_written_is_always_promised(
    tracked: set[str], spans: list[str]
) -> None:
    """For any tracked files and spans, a file span that is a tracked path is promised and a folder promises its files."""
    text = " ".join(f"`{s}`" for s in spans)
    promised = set(promised_files(text, "alpha", tracked))
    assert {s for s in spans if s in tracked} <= promised
    for folder in spec_folders(text):
        assert {p for p in tracked if p.startswith(folder)} <= promised


@pytest.mark.property
@given(tracked=TRACKED, spans=SPANS, seed=st.randoms(use_true_random=False))
def test_property_the_promises_do_not_depend_on_the_order_the_files_were_listed(
    tracked: set[str], spans: list[str], seed: random.Random
) -> None:
    """For any tracked files listed in any order, the promises are the same."""
    text = " ".join(f"`{s}`" for s in spans)
    shuffled = sorted(tracked)
    seed.shuffle(shuffled)
    assert promised_files(text, "alpha", tracked) == promised_files(text, "alpha", frozenset(shuffled))
