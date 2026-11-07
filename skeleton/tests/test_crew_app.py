"""The Crew app's manifest against the rules in the App Kit documents (``manifest-reference.md``, Validation Rules).

Kiro Crew is not installed here, so these tests check the rules the documents state and nothing Crew itself decides.
They do not show that Crew accepts the app.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath
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


def cron_problems(cron: dict[str, Any], agent_names: set[str]) -> list[str]:
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
                agent_names.add(str(json.loads((root / relative).read_text(encoding="utf-8")).get("name")))
    crons = manifest.get("crons", [])
    if crons and manifest.get("permissions", {}).get("cron") is not True:
        problems.append('crons need "cron": true under permissions')
    names = [c.get("name") for c in crons]
    if len(set(names)) != len(names):
        problems.append("cron names are not unique")
    for cron in crons:
        problems.extend(cron_problems(cron, agent_names))
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


def test_the_night_audit_cron_fires_at_0200_utc_on_the_minute_with_a_stated_timeout(manifest: dict[str, Any]) -> None:
    cron = cron_named(manifest, "night-audit")
    assert (cron["cron_expr"], cron["timezone"], cron["strict_schedule"]) == ("0 2 * * *", "UTC", True)
    assert "every" not in cron
    assert cron["timeout"] == 1200 and cron["timeout_secs"] >= cron["timeout"] + 5
    assert "scripts/nightly.py" in cron["command"]


def test_the_investigator_cron_runs_after_the_audit_with_the_investigator_agent_and_a_stated_timeout(
    manifest: dict[str, Any],
) -> None:
    audit, investigator = cron_named(manifest, "night-audit"), cron_named(manifest, "night-investigator")
    assert investigator["agent"] == "night-investigator" and investigator["timezone"] == "UTC"
    assert investigator["strict_schedule"] is True and 1 <= investigator["timeout_secs"] <= 86400

    def minutes(expr: str) -> int:
        minute, hour, *rest = expr.split()
        assert rest == ["*", "*", "*"]
        return int(hour) * 60 + int(minute)

    gap = minutes(investigator["cron_expr"]) - minutes(audit["cron_expr"])
    assert gap * 60 > audit["timeout_secs"], "the investigator starts after the audit's whole time limit has passed"


def test_both_crons_are_registered_paused_until_the_checkout_path_is_set(manifest: dict[str, Any]) -> None:
    assert all(c["enabled"] is False for c in manifest["crons"])
    assert "REPLACE_WITH_NIGHT_AUDIT_CHECKOUT" in cron_named(manifest, "night-audit")["command"]
    assert "REPLACE_WITH_NIGHT_AUDIT_CHECKOUT" in " ".join(manifest["configuration"]) or "checkout" in " ".join(
        manifest["configuration"]
    )


def test_the_permissions_are_the_one_the_documents_require_for_crons_and_nothing_else(manifest: dict[str, Any]) -> None:
    assert manifest["permissions"] == {"cron": True}


def test_the_investigator_agent_declares_only_read_tools_and_ships_no_grant() -> None:
    agent = json.loads((APP / "agents" / "night-investigator.json").read_text(encoding="utf-8"))
    assert agent["name"] == "night-investigator"
    assert set(agent["tools"]) <= READ_ONLY_TOOLS and agent["tools"]
    assert not GRANT_KEYS & agent.keys()
    assert "malicious" in agent["prompt"] and "data, never an instruction" in agent["prompt"]


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
        (lambda m: m["crons"][0].update(script="a.py:f"), "mutually exclusive"),
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

    def fake_main(argv: list[str]) -> int:
        seen.append(Path(argv[1]).name)
        if argv[1].endswith("a.yaml"):
            raise RuntimeError("source unreachable")
        return 0

    monkeypatch.setattr(nightly, "nightaudit_main", fake_main)
    assert nightly.main(["--apps-dir", str(tmp_path), "--runs", str(tmp_path / "runs")]) == 1
    assert seen == ["a.yaml", "b.yaml"]
    assert "FAILED a.yaml: RuntimeError: source unreachable" in capsys.readouterr().err
    assert nightly.main(["--apps-dir", str(tmp_path / "nothing")]) == 1


def test_the_readme_gives_the_documented_install_steps_and_does_not_claim_a_run() -> None:
    text = README.read_text(encoding="utf-8")
    for step in ("kirocrew gateway", "kirocrew app install /absolute/path/to/night-audit/crew/night-shift",
                 "kirocrew app enable night-shift", "Third-party apps"):  # fmt: skip
        assert step in text
    assert "has not run them" in text and "Nothing here has been installed, enabled or scheduled" in text
    for claim in ("has run", "was tested", "was installed", "works in Crew", "verified in Crew", "successfully"):
        assert claim not in text, claim
