"""Which backticked spans in a spec name a file, and one spelling for a repository path (audit rule 6).

The parser cases are in the casebook, written before the parser. The properties hold for any text.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st
from own_build.paths import canonical_path, file_path_in, spec_paths
from own_build_testkit import CASEBOOK

CASES: list[dict[str, Any]] = yaml.safe_load(CASEBOOK.read_text(encoding="utf-8"))["parser"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_the_parser_reads_exactly_the_files_the_casebook_says_a_text_names(case: dict[str, Any]) -> None:
    assert spec_paths(case["text"]) == sorted(case["expect"])


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
