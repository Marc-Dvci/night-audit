"""The Kiro hook scripts: what they block and what they let through."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "scripts" / "hooks"
HOOK_FILES = sorted((ROOT / ".kiro" / "hooks").glob("*"))
#: The triggers the hook files in this repository use. A file with any other trigger never fires.
KNOWN_TRIGGERS = frozenset({"PreToolUse", "PostToolUse", "PostFileSave", "UserPromptSubmit", "Stop"})
#: A matcher of only ``*`` is the "every tool" wildcard, not a regular expression.
WILDCARD = "*"


@pytest.mark.parametrize("path", HOOK_FILES, ids=lambda p: p.name)
def test_a_hook_file_kiro_would_skip_silently_fails_here_instead(path: Path) -> None:
    """Kiro skips a hook file it cannot read without saying so. Two were invalid JSON for three days unnoticed.

    Every file in ``.kiro/hooks/`` must be JSON, name a known trigger for each hook, and give each hook a matcher that
    is the wildcard or a regular expression that compiles.
    """
    assert path.suffix == ".json", f"{path.name}: hook files are .json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"{path.name} is not valid JSON, so Kiro skips it silently: {exc}")
    hooks = data.get("hooks") if isinstance(data, dict) else None
    assert isinstance(hooks, list) and hooks, f"{path.name}: needs a non-empty 'hooks' list"
    for hook in hooks:
        name = hook.get("name", "?")
        assert hook.get("trigger") in KNOWN_TRIGGERS, f"{path.name}/{name}: unknown trigger {hook.get('trigger')!r}"
        action = hook.get("action")
        assert isinstance(action, dict) and action.get("type") in {"command", "agent"}, f"{path.name}/{name}: action"
        matcher = hook.get("matcher")
        if matcher is None or matcher == WILDCARD:
            continue
        assert isinstance(matcher, str), f"{path.name}/{name}: matcher must be a string"
        try:
            re.compile(matcher)
        except re.error as exc:
            pytest.fail(f"{path.name}/{name}: matcher {matcher!r} does not compile: {exc}")


def test_there_are_hook_files_to_check() -> None:
    assert len(HOOK_FILES) >= 6


@pytest.mark.parametrize(
    "text",
    [
        # A trailing comma, the mistake that kept two hooks from loading.
        '{"version": "v1", "hooks": [{"name": "x", "trigger": "PostFileSave", "matcher": "a\\.py$",}]}',
        '{"version": "v1", "hooks": [{"name": "x", "trigger": "OnSave", "action": {"type": "command"}}]}',
        '{"version": "v1", "hooks": [{"name": "x", "trigger": "PreToolUse", "matcher": "(mcp_",'
        ' "action": {"type": "command"}}]}',
    ],
    ids=["invalid-json", "unknown-trigger", "matcher-does-not-compile"],
)
def test_the_hook_check_fails_on_each_kind_of_broken_file(tmp_path: Path, text: str) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text(text, encoding="utf-8")
    with pytest.raises((pytest.fail.Exception, AssertionError)):
        test_a_hook_file_kiro_would_skip_silently_fails_here_instead(broken)


def _run(script: str, tool: str, tool_input: dict[str, object]) -> int:
    event = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOKS / script)], input=event, text=True, capture_output=True, check=False
    ).returncode


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
def test_read_only_guard_checks_mcp_aws_tools() -> None:
    assert _run("readonly_guard.py", "mcp_aws-api_call_aws", {"cli_command": "aws ec2 run-instances --count 1"}) == 2
    assert _run("readonly_guard.py", "mcp_aws-api_call_aws", {"cli_command": "aws ec2 describe-regions"}) == 0


@pytest.mark.integration
def test_no_harm_guard_refuses_a_delete_command() -> None:
    assert _run("no_harm_guard.py", "execute_pwsh", {"command": "Remove-Item -Recurse build"}) == 2


@pytest.mark.integration
def test_no_harm_guard_refuses_a_push() -> None:
    assert _run("no_harm_guard.py", "execute_pwsh", {"command": "git push origin main"}) == 2


@pytest.mark.integration
def test_no_harm_guard_allows_a_piped_build_command() -> None:
    command = "npm run build 2>&1 | Select-Object -Last 20"
    assert _run("no_harm_guard.py", "execute_pwsh", {"command": command}) == 0
