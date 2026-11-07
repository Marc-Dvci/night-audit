"""The Crew app's manifest against the App Kit documents and the Kiro Crew 0.13.0 source that registers it.

The documents are ``manifest-reference.md``; where they and the source differ, these tests follow the source
(``build/crew-docs/src/``): ``bridges_crons.py`` and ``cron_script_paths.py`` for script crons, ``bridges_agents.py``
for an agent's ``@server`` tool refs and host placeholders. The cron callables in ``crons/night_jobs.py`` are run here
with the subprocess stubbed at the edge.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "crew" / "night-shift"
README = ROOT / "crew" / "README.md"
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED = {"system", "library", "registry", "registries", "blob", "install", "register"}
WINDOWS_DEVICES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
REQUIRED = ("name", "version", "displayName", "description")
RECOMMENDED = ("author", "license", "tags", "highlights", "useCases", "configuration")
CRON_FIELDS = {
    "name", "every", "cron_expr", "message", "agent", "agent_sequence", "command", "script", "env", "persistent_session",
    "silent", "folder", "timezone", "skip_dates", "timeout", "timeout_secs", "strict_schedule", "enabled",
}  # fmt: skip
#: Tools the agent may declare. None of them writes to the account or the repository.
READ_ONLY_TOOLS = {"read", "@aws-api", "@aws-cloudtrail"}
#: Keys a bundled agent file may not carry: Crew refuses a grant that ships inside the bundle.
GRANT_KEYS = {"allowedTools", "autoApprove", "permissions"}
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
CRON_FIELD = re.compile(r"[0-9*/,\-]+")
#: The only ``{UPPER_CASE}`` placeholders Crew renders in an agent file (``bridges_agents.HOST_PLACEHOLDERS``). An agent
#: naming any other one is not registered; ``${AWS_PROFILE}`` contains ``{AWS_PROFILE}``.
HOST_PLACEHOLDERS = {"{APP_ROOT}", "{APP_DATA}", "{UV_BIN}", "{HOST_PATH}", "{PATH_SEP}"}
PLACEHOLDER = re.compile(r"\{[A-Z][A-Z0-9_]*\}")


def script_problems(root: Path, label: str, spec: object) -> list[str]:
    """Why a cron's ``script`` would not resolve in Crew (``cron_script_paths.resolve_script_path``), or ``[]``.

    Split on the last colon, as Crew does, so a drive letter stays with the path.
    """
    drive = isinstance(spec, str) and len(spec) >= 2 and spec[1] == ":" and spec[0].isalpha()
    if not isinstance(spec, str) or spec.rfind(":") == -1 or (drive and spec.rfind(":") == 1):
        return [f"{label}: script must be a string file.py:function"]
    module, _, func = spec.rpartition(":")
    reason = inside_app(root, module)
    if reason is not None:
        return [f"{label}: script path {module!r} {reason}"]
    if not module.lower().endswith(".py"):
        return [f"{label}: script must name a .py file"]
    tree = ast.parse((root / module).read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if func not in names:
        return [f"{label}: script function {func!r} is not defined in {module}"]
    return []


def agent_problems(agent: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    """What Crew warns about or refuses when it registers *agent* (``bridges_agents``)."""
    label = f"agent {agent.get('name')!r}"
    problems: list[str] = []
    declared = set(agent.get("mcpServers") or {})
    declared |= {f"{manifest.get('name')}:{n}" for n in manifest.get("mcpServers") or {}}
    for tool in agent.get("tools") or []:
        if isinstance(tool, str) and tool.startswith("@"):
            server = tool[1:].split("/", 1)[0]
            if server not in declared:
                problems.append(f"{label}: tool ref {tool} has no declared server {server!r}")
    for found in set(PLACEHOLDER.findall(json.dumps(agent))) - HOST_PLACEHOLDERS:
        problems.append(f"{label}: unresolved placeholder {found}")
    return problems


def inside_app(root: Path, relative: object) -> str | None:
    """Why *relative* is not a path inside the app root that exists, or ``None``."""
    if not isinstance(relative, str) or not relative:
        return "is not a non-empty string"
    pure = PurePosixPath(relative)
    if pure.is_absolute() or PureWindowsLike(relative) or ".." in pure.parts:
        return "is absolute or leaves the app root"
    target = (root / relative).resolve()
    if root.resolve() not in target.parents:
        return "leaves the app root"
    return None if target.exists() else "does not exist"


def PureWindowsLike(text: str) -> bool:  # noqa: N802 - reads as a predicate
    return bool(re.match(r"^[A-Za-z]:|^\\\\|\\", text))


def cron_problems(cron: dict[str, Any], agent_names: set[str], root: Path = APP) -> list[str]:
    label = f"cron {cron.get('name')!r}"
    problems: list[str] = []
    for key in cron.keys() - CRON_FIELDS:
        problems.append(f"{label}: unknown field {key}")
    if not isinstance(cron.get("name"), str) or not cron.get("name"):
        problems.append(f"{label}: no name")
    if ("every" in cron) == ("cron_expr" in cron):
        problems.append(f"{label}: needs exactly one of every and cron_expr")
    if "every" in cron and (isinstance(cron["every"], bool) or not isinstance(cron["every"], int | float)):
        problems.append(f"{label}: every is not a number")
    if "cron_expr" in cron:
        parts = str(cron["cron_expr"]).split()
        if len(parts) != 5 or not all(CRON_FIELD.fullmatch(p) for p in parts):
            problems.append(f"{label}: cron_expr is not five cron fields")
    if "timezone" in cron:
        try:
            ZoneInfo(str(cron["timezone"]))
        except (ZoneInfoNotFoundError, ValueError):
            problems.append(f"{label}: {cron['timezone']!r} is not an IANA zone")
    for key in ("strict_schedule", "enabled", "persistent_session", "silent"):
        if key in cron and not isinstance(cron[key], bool):
            problems.append(f"{label}: {key} must be a JSON boolean")
    for date in cron.get("skip_dates", []):
        if not isinstance(date, str) or not DATE.fullmatch(date):
            problems.append(f"{label}: skip date {date!r} is not zero-padded YYYY-MM-DD")
    if "command" in cron and "script" in cron:
        problems.append(f"{label}: command and script are mutually exclusive")
    if "script" in cron:
        problems.extend(script_problems(root, label, cron["script"]))
    total = cron.get("timeout_secs")
    if total is not None and (isinstance(total, bool) or not isinstance(total, int) or not 1 <= total <= 86400):
        problems.append(f"{label}: timeout_secs is not within 1..86400")
    if "command" in cron or "script" in cron:
        subprocess_limit = cron.get("timeout") or (300 if "command" in cron else 30)
        if not isinstance(total, int) or total < subprocess_limit + 5:
            problems.append(f"{label}: timeout_secs must cover timeout plus 5 seconds of cleanup")
    if "agent" in cron and cron["agent"] not in agent_names:
        problems.append(f"{label}: agent {cron['agent']!r} is not declared in agents")
    return problems


def manifest_problems(manifest: dict[str, Any], root: Path = APP) -> list[str]:
    problems: list[str] = []
    for field in REQUIRED:
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            problems.append(f"{field} must be a non-empty string")
    name = str(manifest.get("name", ""))
    if not NAME.fullmatch(name):
        problems.append("name is not kebab-case")
    if name in RESERVED or name in WINDOWS_DEVICES:
        problems.append("name is reserved")
    if not re.match(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
        problems.append("version does not start with MAJOR.MINOR.PATCH")
    for field in RECOMMENDED:
        if not manifest.get(field):
            problems.append(f"recommended field {field} is missing")
    for field in ("tags", "highlights", "useCases", "configuration"):
        value = manifest.get(field, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            problems.append(f"{field} must be a list of strings")
    agent_names: set[str] = set()
    for field in ("agents", "skills"):
        for relative in manifest.get(field, []):
            reason = inside_app(root, relative)
            if reason is not None:
                problems.append(f"{field} path {relative!r} {reason}")
            elif field == "agents":
                agent = json.loads((root / relative).read_text(encoding="utf-8"))
                agent_names.add(str(agent.get("name")))
                problems.extend(agent_problems(agent, manifest))
    crons = manifest.get("crons", [])
    if crons and manifest.get("permissions", {}).get("cron") is not True:
        problems.append('crons need "cron": true under permissions')
    names = [c.get("name") for c in crons]
    if len(set(names)) != len(names):
        problems.append("cron names are not unique")
    for cron in crons:
        problems.extend(cron_problems(cron, agent_names, root))
    return problems


@pytest.fixture
def manifest() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((APP / "app.json").read_text(encoding="utf-8"))
    return loaded


def cron_named(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    (found,) = [c for c in manifest["crons"] if c["name"] == name]
    cron: dict[str, Any] = found
    return cron


def test_the_manifest_follows_the_documented_rules(manifest: dict[str, Any]) -> None:
    assert manifest_problems(manifest) == []
    assert manifest["name"] == APP.name
    assert set(manifest) >= {*REQUIRED, *RECOMMENDED, "permissions", "agents", "skills", "crons"}


def test_the_night_audit_cron_fires_at_0200_utc_on_the_minute_as_a_script_with_a_stated_timeout(
    manifest: dict[str, Any],
) -> None:
    cron = cron_named(manifest, "night-audit")
    assert (cron["cron_expr"], cron["timezone"], cron["strict_schedule"]) == ("0 2 * * *", "UTC", True)
    assert "every" not in cron and "command" not in cron
    assert cron["script"] == "crons/night_jobs.py:nightly"
    assert cron["timeout"] == 1500 and cron["timeout_secs"] >= cron["timeout"] + 5
    jobs = load_jobs()
    assert jobs.NIGHTLY_TIMEOUT < cron["timeout"], "the audit's own limit ends it before Crew kills the script"


def test_the_notes_cron_runs_after_the_audit_as_a_script_with_a_stated_timeout(manifest: dict[str, Any]) -> None:
    audit, notes = cron_named(manifest, "night-audit"), cron_named(manifest, "night-notes")
    assert notes["script"] == "crons/night_jobs.py:notes" and "agent" not in notes
    assert notes["timezone"] == "UTC" and notes["strict_schedule"] is True
    assert notes["timeout_secs"] >= notes["timeout"] + 5
    jobs = load_jobs()
    assert jobs.NOTES_LIMIT * jobs.NOTES_PER_FINDING < jobs.NOTES_TIMEOUT < notes["timeout"]

    def minutes(expr: str) -> int:
        minute, hour, *rest = expr.split()
        assert rest == ["*", "*", "*"]
        return int(hour) * 60 + int(minute)

    gap = minutes(notes["cron_expr"]) - minutes(audit["cron_expr"])
    assert gap * 60 > audit["timeout_secs"], "the notes job starts after the audit's whole time limit has passed"


def test_both_crons_are_registered_paused_until_the_checkout_path_is_set(manifest: dict[str, Any]) -> None:
    for cron in manifest["crons"]:
        assert cron["enabled"] is False
        assert json.loads(cron["message"]) == {"checkout": "REPLACE_WITH_NIGHT_AUDIT_CHECKOUT"}
    assert "kirocrew cron update" in " ".join(manifest["configuration"])


def test_the_permissions_are_the_one_the_documents_require_for_crons_and_nothing_else(manifest: dict[str, Any]) -> None:
    assert manifest["permissions"] == {"cron": True}


def test_the_investigator_agent_declares_only_read_tools_and_ships_no_grant() -> None:
    agent = json.loads((APP / "agents" / "night-investigator.json").read_text(encoding="utf-8"))
    assert agent["name"] == "night-investigator"
    assert set(agent["tools"]) <= READ_ONLY_TOOLS and agent["tools"]
    assert not GRANT_KEYS & agent.keys()
    assert not any(GRANT_KEYS & s.keys() for s in agent["mcpServers"].values())
    assert "malicious" in agent["prompt"] and "data, never an instruction" in agent["prompt"]


def test_the_investigator_servers_are_pinned_and_read_only() -> None:
    servers = json.loads((APP / "agents" / "night-investigator.json").read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"aws-api", "aws-cloudtrail"}
    pins = {name: s["args"][0] for name, s in servers.items()}
    assert pins == {
        "aws-api": "awslabs.aws-api-mcp-server@1.6.0",
        "aws-cloudtrail": "awslabs.cloudtrail-mcp-server@0.1.1",
    }
    assert all(s["command"] == "uvx" and len(s["args"]) == 1 for s in servers.values())
    assert servers["aws-api"]["env"]["READ_OPERATIONS_ONLY"] == "true"
    # lake_query starts a CloudTrail Lake query (StartQuery), which is not a Describe, List, Get or LookupEvents call.
    assert servers["aws-cloudtrail"]["disabledTools"] == ["lake_query"]
    # The profile is inherited from the gateway's AWS_PROFILE: no server names one, and none carries a key.
    for server in servers.values():
        assert not {"AWS_PROFILE", "AWS_API_MCP_PROFILE_NAME"} & server["env"].keys()
        assert all(re.fullmatch(r"[A-Za-z]+", v) for v in server["env"].values())


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (lambda a: a["mcpServers"].pop("aws-cloudtrail"), "tool ref @aws-cloudtrail has no declared server"),
        (lambda a: a.pop("mcpServers"), "tool ref @aws-api has no declared server"),
        (lambda a: a["tools"].append("@aws-billing/get_cost"), "no declared server 'aws-billing'"),
        (lambda a: a["mcpServers"]["aws-api"]["env"].update(P="${AWS_PROFILE}"), "unresolved placeholder"),
    ],
)
def test_the_validator_refuses_an_agent_crew_would_not_mount(manifest: dict[str, Any], edit: Any, problem: str) -> None:
    agent = json.loads((APP / "agents" / "night-investigator.json").read_text(encoding="utf-8"))
    assert agent_problems(agent, manifest) == []
    edit(agent)
    assert any(problem in p for p in agent_problems(agent, manifest)), agent_problems(agent, manifest)


def test_a_tool_ref_to_an_app_level_server_uses_its_namespaced_name(manifest: dict[str, Any]) -> None:
    agent = {"name": "x", "tools": ["@night-shift:own"]}
    assert agent_problems(agent, {**manifest, "mcpServers": {"own": {"command": "python"}}}) == []
    assert agent_problems(agent, manifest) != []


def test_regression_a_command_cron_is_rejected_on_windows_so_the_audit_is_a_script_cron(
    manifest: dict[str, Any],
) -> None:
    """Bug: Crew 0.13.0 on Windows logged "cron 'night-shift/night-audit' command rejected: Error: No POSIX shell
    available to run this command cron" and never registered the audit. A script cron runs on every platform."""
    assert not [c["name"] for c in manifest["crons"] if "command" in c]
    assert all("script" in c for c in manifest["crons"])


def test_regression_the_investigator_tool_refs_name_servers_the_agent_declares(manifest: dict[str, Any]) -> None:
    """Bug: Crew 0.13.0 logged "agent 'night-investigator' grants MCP tool ref(s) not found in this agent's merged
    mcpServers or the global mcp.json; kiro-cli will silently never mount them: @aws-api (server 'aws-api'),
    @aws-cloudtrail (server 'aws-cloudtrail')"."""
    agent = json.loads((APP / "agents" / "night-investigator.json").read_text(encoding="utf-8"))
    refs = {t[1:] for t in agent["tools"] if t.startswith("@")}
    assert refs == {"aws-api", "aws-cloudtrail"} and refs <= set(agent["mcpServers"])


def test_regression_the_agent_file_names_no_placeholder_crew_cannot_render() -> None:
    """Bug: the first fix copied the power's ``"${AWS_PROFILE}"``; Crew 0.13.0 then said "agent night-investigator.json
    has an unresolved placeholder {AWS_PROFILE} — not registered"."""
    text = (APP / "agents" / "night-investigator.json").read_text(encoding="utf-8")
    assert set(PLACEHOLDER.findall(text)) <= HOST_PLACEHOLDERS


def test_the_skill_has_frontmatter_and_names_no_value_it_cannot_cite() -> None:
    text = (APP / "skills" / "read-a-night" / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert front is not None and "description:" in front.group(1)


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (lambda m: m.pop("permissions"), 'crons need "cron": true'),
        (lambda m: m["permissions"].update(cron=False), 'crons need "cron": true'),
        (lambda m: m["crons"][0].update(every=300), "exactly one of every and cron_expr"),
        (lambda m: m["crons"][0].pop("cron_expr"), "exactly one of every and cron_expr"),
        (lambda m: m["crons"][0].update(timezone="Mars/Olympus"), "not an IANA zone"),
        (lambda m: m["crons"][0].update(strict_schedule="yes"), "must be a JSON boolean"),
        (lambda m: m["crons"][0].update(skip_dates=["2026-1-1"]), "zero-padded"),
        (lambda m: m["crons"][0].update(timeout_secs=1200), "must cover timeout"),
        (lambda m: m["crons"][0].update(command="uv run python scripts/nightly.py"), "mutually exclusive"),
        (lambda m: m["crons"][0].update(script="../outside.py:nightly"), "leaves the app root"),
        (lambda m: m["crons"][0].update(script="C:/night_jobs.py:nightly"), "absolute"),
        (lambda m: m["crons"][0].update(script="crons/missing.py:nightly"), "does not exist"),
        (lambda m: m["crons"][0].update(script="app.json:nightly"), "must name a .py file"),
        (lambda m: m["crons"][0].update(script="crons/night_jobs.py:nowhere"), "is not defined"),
        (lambda m: m["crons"][0].update(script="crons/night_jobs.py"), "file.py:function"),
        (lambda m: m["crons"][0].update(timeout=1600), "must cover timeout"),
        (lambda m: m["crons"][1].update(agent="someone-else"), "is not declared in agents"),
        (lambda m: m["agents"].append("agents/missing.json"), "does not exist"),
        (lambda m: m["agents"].append("../outside.json"), "leaves the app root"),
        (lambda m: m["skills"].append("/etc"), "absolute"),
        (lambda m: m.update(name="Night_Shift"), "not kebab-case"),
        (lambda m: m.update(name="library"), "reserved"),
        (lambda m: m.update(name="nul"), "reserved"),
        (lambda m: m.update(version="one"), "MAJOR.MINOR.PATCH"),
        (lambda m: m.update(displayName=" "), "displayName must be a non-empty string"),
        (lambda m: m.pop("license"), "license is missing"),
        (lambda m: m["crons"].append(copy.deepcopy(m["crons"][0])), "not unique"),
    ],
)
def test_the_validator_refuses_each_documented_mistake(manifest: dict[str, Any], edit: Any, problem: str) -> None:
    edit(manifest)
    assert any(problem in p for p in manifest_problems(manifest)), manifest_problems(manifest)


def load_nightly() -> Any:
    spec = importlib.util.spec_from_file_location("nightly", ROOT / "scripts" / "nightly.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["nightly"] = module
    spec.loader.exec_module(module)
    return module


def test_the_nightly_script_runs_controls_and_skips_settings_files(tmp_path: Path) -> None:
    nightly = load_nightly()
    controls = tmp_path / "demo" / "controls"
    controls.mkdir(parents=True)
    (controls / "a-control.yaml").write_text("id: a\nledgers: {}\n", encoding="utf-8")
    (controls / "settings.local.yaml").write_text("region: us-east-1\n", encoding="utf-8")
    (controls / "broken.yaml").write_text("a: [unclosed\n", encoding="utf-8")
    assert nightly.find_controls(tmp_path) == [controls / "a-control.yaml"]

    real = {p.name for p in nightly.find_controls(ROOT / "apps")}
    assert {"aws-account.yaml", "staff-access.yaml"} <= real
    assert not {n for n in real if "settings" in n or "exclusions" in n or "scope" in n}


def test_the_nightly_script_runs_every_control_even_after_one_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    nightly = load_nightly()
    controls = tmp_path / "demo" / "controls"
    controls.mkdir(parents=True)
    for name in ("a", "b"):
        (controls / f"{name}.yaml").write_text("ledgers: {}\n", encoding="utf-8")
    seen: list[str] = []

    def stub_main(argv: list[str]) -> int:
        seen.append(Path(argv[1]).name)
        if argv[1].endswith("a.yaml"):
            raise RuntimeError("source unreachable")
        return 0

    monkeypatch.setattr(nightly, "nightaudit_main", stub_main)
    assert nightly.main(["--apps-dir", str(tmp_path), "--runs", str(tmp_path / "runs")]) == 1
    assert seen == ["a.yaml", "b.yaml"]
    assert "FAILED a.yaml: RuntimeError: source unreachable" in capsys.readouterr().err
    assert nightly.main(["--apps-dir", str(tmp_path / "nothing")]) == 1


def load_jobs() -> Any:
    spec = importlib.util.spec_from_file_location("night_jobs", APP / "crons" / "night_jobs.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["night_jobs"] = module
    spec.loader.exec_module(module)
    return module


def stub_checkout(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "nightly.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    return tmp_path


def ctx_for(checkout: object) -> SimpleNamespace:
    return SimpleNamespace(job=SimpleNamespace(id="abc123", message=json.dumps({"checkout": str(checkout)})))


class StubRun:
    """The subprocess edge: records each call and returns or raises what it was given."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "", raises: Exception | None = None):
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.raises = raises

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, kwargs))
        if self.raises is not None:
            raise self.raises
        return self.result


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch) -> Any:
    module = load_jobs()
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/bin/{name}")
    return module


def test_the_audit_job_runs_nightly_py_through_uv_as_an_argument_list_and_reports_its_output(
    jobs: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = stub_checkout(tmp_path)
    monkeypatch.setenv("VIRTUAL_ENV", "/gateway/.venv")
    run = StubRun(stdout="run 1e9e38e57a33f5c4\n  complete: True\n")
    with pytest.raises(jobs.Report) as reported:
        jobs.nightly(ctx_for(checkout), run=run)
    ((argv, kwargs),) = run.calls
    assert argv == ["/bin/uv", "run", "--directory", str(checkout), "python", "scripts/nightly.py", "--runs", "runs"]
    assert "shell" not in kwargs and kwargs["timeout"] == jobs.NIGHTLY_TIMEOUT and kwargs["check"] is False
    assert "VIRTUAL_ENV" not in kwargs["env"]
    assert "run 1e9e38e57a33f5c4" in reported.value.message


def test_the_audit_job_fails_with_the_exit_code_and_the_output_tail_when_nightly_py_fails(
    jobs: Any, tmp_path: Path
) -> None:
    run = StubRun(returncode=1, stderr="FAILED aws-account.yaml: RuntimeError: source unreachable")
    with pytest.raises(jobs.JobFailed, match=r"exited with code 1: .*source unreachable"):
        jobs.nightly(ctx_for(stub_checkout(tmp_path)), run=run)


@pytest.mark.parametrize(
    ("message", "says"),
    [
        ('{"checkout": "REPLACE_WITH_NIGHT_AUDIT_CHECKOUT"}', "is not an absolute path"),
        ("Run nightaudit for each control", "must be JSON like"),
        ('{"path": "D:/night-audit"}', "must be JSON like"),
        ("", "must be JSON like"),
    ],
)
def test_a_job_whose_message_names_no_checkout_fails_with_one_line_and_runs_nothing(
    jobs: Any, message: str, says: str
) -> None:
    run = StubRun()
    with pytest.raises(jobs.JobFailed, match=says) as failed:
        jobs.nightly(SimpleNamespace(job=SimpleNamespace(id="x", message=message)), run=run)
    assert "\n" not in str(failed.value) and run.calls == []


def test_a_checkout_that_is_missing_fails_with_one_line_and_runs_nothing(jobs: Any, tmp_path: Path) -> None:
    run = StubRun()
    with pytest.raises(jobs.JobFailed, match="is not a Night Audit checkout") as failed:
        jobs.notes(ctx_for(tmp_path / "nowhere"), run=run)
    assert "\n" not in str(failed.value) and run.calls == []


def test_a_job_that_runs_too_long_fails_with_its_time_limit(jobs: Any, tmp_path: Path) -> None:
    run = StubRun(raises=subprocess.TimeoutExpired(["uv"], 1440))
    with pytest.raises(jobs.JobFailed, match=r"scripts/nightly.py did not finish within 1440 s"):
        jobs.nightly(ctx_for(stub_checkout(tmp_path)), run=run)


def test_a_job_fails_with_one_line_when_uv_is_not_on_the_path(
    jobs: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs.shutil, "which", lambda name: None)
    with pytest.raises(jobs.JobFailed, match="uv is not on the gateway's PATH"):
        jobs.nightly(ctx_for(stub_checkout(tmp_path)), run=StubRun())


def test_the_notes_job_runs_night_shift_py_with_its_limits_and_the_gateway_profile(
    jobs: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_PROFILE", "night-audit")
    run = StubRun(stdout="run 1e9e38e57a33f5c4: 5 accepted, 0 rejected, 0 unavailable, 0 skipped")
    with pytest.raises(jobs.Report, match="5 accepted"):
        jobs.notes(ctx_for(stub_checkout(tmp_path)), run=run)
    ((argv, kwargs),) = run.calls
    assert argv[5:] == [
        "scripts/night_shift.py", "--runs", "runs", "--limit", "12", "--timeout", "240", "--profile", "night-audit"
    ]  # fmt: skip
    assert kwargs["timeout"] == jobs.NOTES_TIMEOUT


def test_the_notes_job_fails_when_kiro_was_unavailable_for_a_finding(jobs: Any, tmp_path: Path) -> None:
    run = StubRun(returncode=2, stdout="unavailable  lab-debug: kiro-cli exited with code 3")
    with pytest.raises(jobs.JobFailed, match="exited with code 2: .*kiro-cli exited with code 3"):
        jobs.notes(ctx_for(stub_checkout(tmp_path)), run=run)


def test_the_job_file_passes_crews_body_scan_patterns() -> None:
    """Crew refuses a script body that names a credential path, a protected secret variable or a URL
    (``mcp_cron_vet._vet_script_contents``); Crew's own scan passed on this file on 7 Nov 2026."""
    text = (APP / "crons" / "night_jobs.py").read_text(encoding="utf-8")
    assert not re.search(r"https?://|\.aws[/\\]|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|AWS_SESSION_TOKEN", text)
    assert "raise Done" not in text, "Done removes the job after the run"


def test_the_readme_gives_the_install_steps_and_records_the_crew_run() -> None:
    text = README.read_text(encoding="utf-8")
    for step in ("kirocrew app install", "kirocrew app enable night-shift", "kirocrew cron update",
                 "kirocrew cron trigger", "kirocrew cron pause"):  # fmt: skip
        assert step in text
    for evidence in ("Crew 0.13.0", "Windows 11", "1e9e38e57a33f5c4", "5 accepted", "Still not checked"):
        assert evidence in text
    for claim in ("works in Crew", "successfully", "fully tested", "production-ready"):
        assert claim not in text, claim
