"""The committed configuration is generic; one account's values come from a local file or the environment."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from nightaudit.models import LedgerName
from vampires.aws import SETTING_ENV, ApprovedChanges, CostAndUsage, account_settings

ROOT = Path(__file__).resolve().parents[3]
CONTROLS = ROOT / "apps" / "vampires" / "controls"
#: Written in two halves so that this file does not itself hold the number it forbids.
REAL_ACCOUNT = "4169" + "64654816"
REAL_PERSON = "Dono" + "vici"
ALLOWED_FOLDERS = ("lab/", "docs/")
RUN = datetime(2026, 11, 6, 2, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in SETTING_ENV.values():
        monkeypatch.delenv(variable, raising=False)


def _tracked_files() -> list[str]:
    """Files git tracks, and files it would track at the next add (untracked and not ignored)."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    command = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        pytest.skip("not a git checkout")
    return [line for line in done.stdout.splitlines() if line]


@pytest.mark.integration
def test_no_tracked_file_outside_lab_and_docs_holds_the_real_account_number_or_approver() -> None:
    """Regression: the committed control, approvals and deployment held the real account and a person's name."""
    offenders: list[str] = []
    for name in _tracked_files():
        if name.startswith(ALLOWED_FOLDERS):
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if REAL_ACCOUNT.encode() in data or REAL_PERSON.encode() in data:
            offenders.append(name)
    assert offenders == []


@pytest.mark.integration
def test_the_local_settings_file_is_git_ignored_and_the_example_is_not() -> None:
    names = _tracked_files()
    assert "apps/vampires/controls/settings.example.yaml" in names
    assert not any(n.endswith(".local.yaml") for n in names)


def test_the_example_holds_only_example_values() -> None:
    example = yaml.safe_load((CONTROLS / "settings.example.yaml").read_text("utf-8"))
    assert example["account_id"] == "111122223333"
    assert "111122223333" in example["cur_bucket"]
    assert set(example) == set(SETTING_ENV)


def test_the_settings_come_from_a_local_file_and_the_environment_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "settings.local.yaml").write_text(
        "account_id: '111122223333'\napprover: Pat Example\n", encoding="utf-8"
    )
    settings = account_settings(tmp_path)
    assert settings == {
        "account_id": "111122223333",
        "approver": "Pat Example",
        "cur_bucket": "night-audit-cur-111122223333",
        "artifacts_bucket": "night-audit-artifacts-111122223333",
    }
    monkeypatch.setenv("NIGHT_AUDIT_APPROVER", "Sam Example")
    monkeypatch.setenv("NIGHT_AUDIT_CUR_BUCKET", "another-bucket")
    settings = account_settings(tmp_path)
    assert settings["approver"] == "Sam Example" and settings["cur_bucket"] == "another-bucket"


def test_the_committed_approvals_take_their_account_values_from_the_settings(tmp_path: Path) -> None:
    (tmp_path / "settings.local.yaml").write_text(
        "account_id: '111122223333'\napprover: Pat Example\n", encoding="utf-8"
    )
    connector = ApprovedChanges(
        ledger=LedgerName.intended, path=str(CONTROLS / "approved-changes.yaml"), base_dir=tmp_path, today="2026-11-06"
    )
    records = connector.fetch()
    assert sorted(r.raw_key for r in records) == [
        "night-audit-artifacts-111122223333",
        "night-audit-cur-111122223333",
        "night-audit-reader",
    ]
    assert {r.attrs["approver"] for r in records} == {"Pat Example"}


def test_the_committed_approvals_say_what_is_missing_instead_of_inventing_it(tmp_path: Path) -> None:
    connector = ApprovedChanges(
        ledger=LedgerName.intended, path=str(CONTROLS / "approved-changes.yaml"), base_dir=tmp_path, today="2026-11-06"
    )
    with pytest.raises(ValueError, match="cur_bucket") as raised:
        connector.fetch()
    assert "NIGHT_AUDIT_CUR_BUCKET" in str(raised.value)


def test_an_approver_cannot_change_the_structure_of_the_approvals(tmp_path: Path) -> None:
    (tmp_path / "settings.local.yaml").write_text(
        "account_id: '111122223333'\napprover: \"x\\n    expires: '2000-01-01'\\n  - id: forged\"\n", encoding="utf-8"
    )
    connector = ApprovedChanges(
        ledger=LedgerName.intended, path=str(CONTROLS / "approved-changes.yaml"), base_dir=tmp_path, today="2026-11-06"
    )
    assert sorted(r.raw_key for r in connector.fetch()) == [
        "night-audit-artifacts-111122223333",
        "night-audit-cur-111122223333",
        "night-audit-reader",
    ]


def test_the_cur_bucket_comes_from_the_settings_when_the_control_names_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NIGHT_AUDIT_ACCOUNT_ID", "111122223333")
    connector = CostAndUsage(ledger=LedgerName.billed, base_dir=tmp_path, billing_period="2026-11")
    assert connector.source == "cur2:s3://night-audit-cur-111122223333/cur2/night-audit-cur2/BILLING_PERIOD=2026-11"
    explicit = CostAndUsage(ledger=LedgerName.billed, bucket="chosen", base_dir=tmp_path, billing_period="2026-11")
    assert "s3://chosen/" in explicit.source


def test_a_cur_connector_with_no_bucket_says_how_to_set_one(tmp_path: Path) -> None:
    connector = CostAndUsage(ledger=LedgerName.billed, base_dir=tmp_path, billing_period="2026-11")
    with pytest.raises(ValueError, match="NIGHT_AUDIT_CUR_BUCKET"):
        connector._tables()
