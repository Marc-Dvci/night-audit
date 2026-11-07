"""The own-build casebook, written before the code, run through the shipped control end to end.

Each case is a tiny repository. The real parser reads its specs, the real connectors read the recorded files, and the
skeleton's runner matches them with the shipped control.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from nightaudit.report import CALM_HEADLINE, headline
from own_build.paths import spec_paths
from own_build_testkit import CASEBOOK, run_in, write_repository

CASES: list[dict[str, Any]] = yaml.safe_load(CASEBOOK.read_text(encoding="utf-8"))["regions"]


def test_the_casebook_has_at_least_five_labelled_cases_and_a_healthy_one() -> None:
    assert len(CASES) >= 5
    assert all(c["id"] and c["note"] and c["expect"] for c in CASES)
    assert any(c["expect"]["findings"] == 0 and c["expect"]["informational"] == 0 for c in CASES)
    regions = {code for c in CASES for code in c["expect"]["regions"].values()}
    assert regions == {"IOB", "OB", "O", "I", "IB", "B", "IO"}, "every region has a case"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_each_casebook_repository_promises_the_files_its_specs_name_as_written(case: dict[str, Any]) -> None:
    written = sorted({path for text in case["specs"].values() for path in spec_paths(text)})
    assert written == sorted(case["expect"]["promised"])


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_the_control_gives_each_casebook_repository_its_labelled_regions(case: dict[str, Any], tmp_path: Path) -> None:
    data = write_repository(tmp_path / "data", case["specs"], case["tracked"], case["kiro"])
    result = run_in(data, tmp_path / "work")
    expect = case["expect"]
    assert result.complete, result.ledger_errors
    assert result.regions == expect["regions"]
    assert sum(1 for f in result.findings if not f.informational) == expect["findings"]
    assert sum(1 for f in result.findings if f.informational) == expect["informational"]
    assert result.billed_total == Decimal(expect["billed_total"])
    if "billed_by_region" in expect:
        assert {c: s.billed_amount for c, s in result.region_summaries.items()} == {
            c: Decimal(v) for c, v in expect["billed_by_region"].items()
        }
    assert result.pending_keys == [] and result.unkeyed == []


def test_a_healthy_repository_reads_calm_and_says_so(tmp_path: Path) -> None:
    case = next(c for c in CASES if c["id"] == "ob-01-healthy-repository")
    data = write_repository(tmp_path / "data", case["specs"], case["tracked"], case["kiro"])
    result = run_in(data, tmp_path / "work")
    assert result.findings == []
    assert headline(result) == CALM_HEADLINE
