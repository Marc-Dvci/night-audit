"""The Kiro power in ``power/night-audit/``: manifest, MCP config, skills, references and the worked example."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from nightaudit.models import DEFAULT_REGION_NAMES, REGION_CODES, LedgerName
from nightaudit.runner import load_control_file, run_control

ROOT = Path(__file__).resolve().parents[2]
POWER = ROOT / "power" / "night-audit"
SKILLS = sorted(p for p in (POWER / "skills").iterdir() if p.is_dir())
ADD_CONTROL = POWER / "skills" / "add-control"
READ_A_NIGHT = POWER / "skills" / "read-a-night"

#: Keys the Agent Plugins 1.0.0 manifest schema allows (``additionalProperties`` is false).
PLUGIN_KEYS = {"$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords", "extensions"}
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
NAME_PATTERN = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
#: What a user types when they need the power (the brief's phrases).
REQUIRED_KEYWORDS = {
    "reconcile",
    "three-way match",
    "audit",
    "orphaned accounts",
    "unused licences",
    "who approved this",
    "billing surprise",
}
REFERENCE = re.compile(r"(?:references|assets)/[A-Za-z0-9_./-]+")
SECRET_SHAPES = re.compile(r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|[A-Za-z0-9/+=]{40}|Bearer\s+\S+|sk-[A-Za-z0-9]{16,}")
ENV_REFERENCE = re.compile(r"^\$\{[A-Z_][A-Z0-9_]*\}$")
#: Fixed, non-secret settings the AWS server may carry as literals.
LITERAL_ENV = {"READ_OPERATIONS_ONLY": "true", "AWS_API_MCP_TELEMETRY": "false", "FASTMCP_LOG_LEVEL": "ERROR"}


def _json(name: str) -> dict[str, Any]:
    data = json.loads((POWER / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path.relative_to(ROOT)} has no frontmatter"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def _named_paths(skill: Path) -> set[str]:
    """Every ``references/...`` or ``assets/...`` path written in the skill's SKILL.md or its reference notes."""
    names: set[str] = set()
    for doc in [skill / "SKILL.md", *sorted((skill / "references").glob("*.md"))]:
        names |= {m.rstrip("./,") for m in REFERENCE.findall(doc.read_text(encoding="utf-8"))}
    return names


# --- plugin.json -------------------------------------------------------------------------------------------------


def test_the_manifest_uses_only_keys_the_schema_allows_and_names_the_plugin_validly() -> None:
    manifest = _json("plugin.json")
    assert manifest["$schema"] == PLUGIN_SCHEMA
    assert set(manifest) <= PLUGIN_KEYS, f"keys the schema does not allow: {sorted(set(manifest) - PLUGIN_KEYS)}"
    assert NAME_PATTERN.fullmatch(manifest["name"]) and len(manifest["name"]) <= 64
    assert manifest["name"] == "night-audit"
    assert manifest["version"] and manifest["description"].strip()
    assert manifest["author"]["name"].strip()
    assert set(manifest["author"]) <= {"name", "email", "url"}


def test_the_keywords_catch_what_a_user_types_when_they_need_the_power() -> None:
    keywords = {k.lower() for k in _json("plugin.json")["keywords"]}
    assert REQUIRED_KEYWORDS <= keywords, f"missing keywords: {sorted(REQUIRED_KEYWORDS - keywords)}"


# --- mcp.json ----------------------------------------------------------------------------------------------------


def test_every_mcp_server_is_a_pinned_stdio_server_that_reads_its_profile_from_the_environment() -> None:
    config = _json("mcp.json")
    assert config["$schema"] == MCP_SCHEMA
    assert set(config) == {"$schema", "mcpServers"}
    servers = config["mcpServers"]
    assert servers, "an empty mcp.json should not exist"
    for name, server in servers.items():
        assert server["type"] == "stdio" and server["command"], f"{name}: type and command are required"
        assert set(server) <= {"type", "command", "args", "env", "cwd"}, f"{name}: keys the schema does not allow"
        assert not any("@latest" in a for a in server.get("args", [])), f"{name}: pin the package version"
        assert any("@" in a and a.rsplit("@", 1)[1][:1].isdigit() for a in server["args"]), f"{name}: no pinned version"
        env = server["env"]
        assert env.get("AWS_API_MCP_PROFILE_NAME") == "${AWS_PROFILE}", f"{name}: the profile is the user's own"
        assert env.get("READ_OPERATIONS_ONLY") == "true", f"{name}: read operations only"


def test_mcp_json_writes_down_no_secret() -> None:
    for name, server in _json("mcp.json")["mcpServers"].items():
        for key, value in server["env"].items():
            assert ENV_REFERENCE.match(value) or LITERAL_ENV.get(key) == value, f"{name}.{key}: literal {value!r}"
            assert not SECRET_SHAPES.search(value), f"{name}.{key} looks like a secret"
        assert not SECRET_SHAPES.search(" ".join(server["args"]))


def test_mcp_json_holds_only_servers_a_skill_uses() -> None:
    skills_text = " ".join((s / "SKILL.md").read_text(encoding="utf-8") for s in SKILLS)
    for name in _json("mcp.json")["mcpServers"]:
        assert re.search(rf"\b{re.escape(name)}\b", skills_text), f"no skill mentions the {name} server"


# --- skills ------------------------------------------------------------------------------------------------------


def test_the_power_has_the_two_skills_the_requirement_names() -> None:
    assert [s.name for s in SKILLS] == ["add-control", "read-a-night"]


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_a_skill_has_frontmatter_whose_name_is_its_folder_and_whose_description_says_when_to_use_it(skill: Path) -> None:
    meta = _frontmatter(skill / "SKILL.md")
    assert meta["name"] == skill.name
    assert NAME_PATTERN.fullmatch(meta["name"]) and len(meta["name"]) <= 64
    description = meta["description"]
    assert isinstance(description, str) and 100 <= len(description) <= 1024
    assert description.startswith("Use when"), "write the description for the moment the user needs the skill"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_every_file_a_skill_names_exists_and_every_file_it_ships_is_named(skill: Path) -> None:
    named = _named_paths(skill)
    assert named, f"{skill.name} names no reference"
    missing = sorted(n for n in named if not (skill / n).exists())
    assert not missing, f"{skill.name} names files that do not exist: {missing}"
    shipped = [
        f.relative_to(skill).as_posix()
        for d in ("references", "assets")
        for f in sorted((skill / d).rglob("*"))
        if f.is_file() and "__pycache__" not in f.parts
    ]
    orphans = [f for f in shipped if not any(f == n or f.startswith(n.rstrip("/") + "/") for n in named)]
    assert not orphans, f"{skill.name} ships files nothing names: {orphans}"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_a_skill_carries_the_region_table_and_the_audit_rules(skill: Path) -> None:
    assert (skill / "references" / "region-table.md").is_file()
    assert (skill / "references" / "audit-rules.md").is_file()


def test_the_shared_references_are_identical_in_both_skills() -> None:
    for name in ("region-table.md", "audit-rules.md"):
        assert (ADD_CONTROL / "references" / name).read_bytes() == (READ_A_NIGHT / "references" / name).read_bytes()


def test_the_region_table_agrees_with_the_package_for_every_region() -> None:
    table = (ADD_CONTROL / "references" / "region-table.md").read_text(encoding="utf-8")
    for code in REGION_CODES:
        row = next((line for line in table.splitlines() if f"| `{code}` |" in line), None)
        assert row, f"region {code} is missing from the table"
        assert DEFAULT_REGION_NAMES[code] in row, f"{code}: the package calls it {DEFAULT_REGION_NAMES[code]}"


def test_the_audit_rules_reference_is_the_steering_file() -> None:
    steering = (ROOT / ".kiro" / "steering" / "audit-rules.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    body = re.sub(r"\A---\n.*?\n---\n", "", steering, flags=re.DOTALL).lstrip("\n")
    assert (ADD_CONTROL / "references" / "audit-rules.md").read_text(encoding="utf-8") == body


def test_add_control_writes_the_casebook_before_the_first_matcher_run() -> None:
    text = (ADD_CONTROL / "SKILL.md").read_text(encoding="utf-8")
    assert text.index("## 4. The casebook, before any matcher run") < text.index("## 5. First run")
    for needle in ("NIGHTAUDIT_SOURCE", "git+https://github.com/Marc-Dvci/night-audit#subdirectory=skeleton", "healthy"):
        assert needle in text


# --- the worked example and the templates ------------------------------------------------------------------------


def test_the_example_control_loads_and_names_the_three_ledgers() -> None:
    control = load_control_file(ADD_CONTROL / "references" / "example-control.yaml")
    assert set(control.ledgers) == {"intended", "observed", "billed"}


def test_the_example_control_finds_each_planted_condition_through_nightaudit(tmp_path: Path) -> None:
    result = run_control(
        ADD_CONTROL / "references" / "example-control.yaml",
        tmp_path,
    )
    assert result.complete and not result.ledger_errors
    assert result.regions == {
        "ana@example-corp.com": "IOB",
        "ben@example-corp.com": "IOB",
        "dev@example-corp.com": "I",
        "eli@example-corp.com": "IB",
        "fay@example-corp.com": "O",
        "gus@example-corp.com": "OB",
        "hal@example-corp.com": "B",
    }


def _project(tmp_path: Path) -> Path:
    """A project that has none of this repository's files: the example and the two templates, as the skill copies them."""
    (tmp_path / "controls").mkdir()
    (tmp_path / "casebook").mkdir()
    (tmp_path / "tests").mkdir()
    refs = ADD_CONTROL / "references"
    shutil.copy(refs / "example-control.yaml", tmp_path / "controls" / "seat-audit.yaml")
    shutil.copytree(refs / "example-fixtures", tmp_path / "controls" / "example-fixtures")
    book = (refs / "example-casebook.yaml").read_text(encoding="utf-8")
    (tmp_path / "casebook" / "seat-audit.yaml").write_text(
        book.replace("control: example-control.yaml", "control: ../controls/seat-audit.yaml"), encoding="utf-8"
    )
    shutil.copy(ADD_CONTROL / "assets" / "casebook_runner.py", tmp_path / "tests" / "test_casebook.py")
    shutil.copy(ADD_CONTROL / "assets" / "contract_tests.py", tmp_path / "tests" / "test_contracts.py")
    return tmp_path


def _pytest(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "--rootdir", str(project), *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.integration
@pytest.mark.timeout(180)
def test_the_copied_templates_pass_on_the_example_in_a_project_with_no_other_night_audit_files(tmp_path: Path) -> None:
    done = _pytest(_project(tmp_path), "tests")
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.integration
@pytest.mark.timeout(180)
def test_the_casebook_runner_refuses_a_casebook_with_no_healthy_case(tmp_path: Path) -> None:
    project = _project(tmp_path)
    book = project / "casebook" / "seat-audit.yaml"
    book.write_text(book.read_text(encoding="utf-8").replace("healthy: true", "healthy: false"), encoding="utf-8")
    done = _pytest(project, "tests/test_casebook.py", "-k", "healthy")
    assert done.returncode != 0 and "healthy: true" in done.stdout


@pytest.mark.integration
@pytest.mark.timeout(180)
def test_the_casebook_runner_fails_a_case_whose_expectation_the_matcher_does_not_meet(tmp_path: Path) -> None:
    project = _project(tmp_path)
    book = project / "casebook" / "seat-audit.yaml"
    book.write_text(book.read_text(encoding="utf-8").replace("gus@example-corp.com: OB}", "gus@example-corp.com: O}", 1), encoding="utf-8")
    done = _pytest(project, "tests/test_casebook.py")
    assert done.returncode != 0 and "ghost-account-with-seat-not-on-roster" in done.stdout


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("connector_template_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # keep the shipped folder free of bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_the_connector_template_is_a_read_only_connector_that_reads_its_recorded_fixture(tmp_path: Path) -> None:
    module = _load_module(ADD_CONTROL / "assets" / "connector_template.py")
    (tmp_path / "observed.json").write_text(
        json.dumps([{"row_id": "a1", "email": "ana@example.test", "timestamp": "2026-03-02T09:00:00Z", "team": "x"}]),
        encoding="utf-8",
    )
    connector = module.ExampleApiLedger(ledger=LedgerName.observed, key_field="email", base_dir=tmp_path, fixture="observed.json")
    assert connector.read_only is True
    [record] = connector.fetch()
    assert (record.row_id, record.raw_key, record.attrs) == ("a1", "ana@example.test", {"team": "x"})
    assert record.timestamp is not None and record.timestamp.year == 2026
