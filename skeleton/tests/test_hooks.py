"""The Kiro hook scripts: what they block and what they let through."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _run(script: str, tool: str, tool_input: dict[str, object]) -> int:
    event = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOKS / script)], input=event, text=True, capture_output=True, check=False
    ).returncode


@pytest.mark.parametrize(
    "path",
    [
        "casebook/heldout/cases.yaml",
        "casebook\\heldout",
        "D:\\repo\\casebook\\heldout\\cases.yaml",
        "./CaseBook/HeldOut/",
    ],
)
def test_seal_blocks_every_spelling_of_the_heldout_folder(path: str) -> None:
    assert _run("seal_heldout.py", "fs_read", {"path": path}) == 2


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("fs_read", {"path": "scripts/hooks/seal_heldout.py"}),  # the hook's own name contains "heldout"
        ("fs_write", {"path": "README.md", "content": "see casebook/heldout"}),
        ("execute_pwsh", {"command": "uv run python scripts/score_heldout.py"}),
        ("fs_read", {"path": "casebook/dev/cases.yaml"}),
    ],
)
def test_seal_lets_ordinary_work_through(tool: str, tool_input: dict[str, object]) -> None:
    assert _run("seal_heldout.py", tool, tool_input) == 0


@pytest.mark.parametrize(
    "command",
    [
        "aws ec2 terminate-instances --instance-ids i-1",
        "aws iam create-access-key --user-name x",
        "aws s3api put-bucket-policy --bucket b --policy file://p.json",
        "aws.exe cloudformation delete-stack --stack-name lab",
    ],
)
def test_read_only_guard_refuses_writes(command: str) -> None:
    assert _run("readonly_guard.py", "execute_pwsh", {"command": command}) == 2


@pytest.mark.parametrize(
    "command",
    [
        "aws ec2 describe-instances --region eu-north-1",
        "aws cloudtrail lookup-events --max-results 5",
        "aws s3api list-objects-v2 --bucket b",
        "uv run pytest -q",
    ],
)
def test_read_only_guard_allows_reads(command: str) -> None:
    assert _run("readonly_guard.py", "execute_pwsh", {"command": command}) == 0


def test_read_only_guard_checks_mcp_aws_tools() -> None:
    assert _run("readonly_guard.py", "mcp_aws-api_call_aws", {"cli_command": "aws ec2 run-instances --count 1"}) == 2
    assert _run("readonly_guard.py", "mcp_aws-api_call_aws", {"cli_command": "aws ec2 describe-regions"}) == 0


def test_no_harm_guard_refuses_a_delete_command() -> None:
    assert _run("no_harm_guard.py", "execute_pwsh", {"command": "Remove-Item -Recurse build"}) == 2


def test_no_harm_guard_refuses_a_push() -> None:
    assert _run("no_harm_guard.py", "execute_pwsh", {"command": "git push origin main"}) == 2


def test_no_harm_guard_allows_a_piped_build_command() -> None:
    command = "npm run build 2>&1 | Select-Object -Last 20"
    assert _run("no_harm_guard.py", "execute_pwsh", {"command": command}) == 0
