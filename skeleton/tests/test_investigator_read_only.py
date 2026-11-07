"""The investigator can call only reads (audit rule 3), checked from its agent file and the MCP settings together.

Two agents investigate: the checkout's ``.kiro/agents/night-investigator.json``, which ``scripts/night_shift.py``
launches through kiro-cli (so the Crew notes job runs it), and the Crew app's own
``crew/night-shift/agents/night-investigator.json``, which Crew registers for chat. Both are checked the same way.

What each pinned server's tools call was read from the server's source in the uv cache (``awslabs/.../server.py``
and ``tools/*.py``) for exactly the versions below. A server or version not recorded here cannot be judged, so it
fails the check; recording a new version means reading its source again.
"""

from __future__ import annotations

import copy
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKOUT_AGENT = ROOT / ".kiro" / "agents" / "night-investigator.json"
CHECKOUT_MCP = ROOT / ".kiro" / "settings" / "mcp.json"
CREW_AGENT = ROOT / "crew" / "night-shift" / "agents" / "night-investigator.json"

EXACT_PIN = re.compile(r"^[A-Za-z0-9_.-]+@\d+(\.\d+)*$")
READ_OPERATION = re.compile(r"^(Describe|List|Get|LookupEvents$|BatchGet)")

#: Tool -> the AWS operations it can call. An empty tuple: the tool makes no call to the account.
#: ``call_aws`` is special: it runs any CLI command, and is a read only with READ_OPERATIONS_ONLY=true.
CALL_AWS = "call_aws"
TOOLS: dict[str, dict[str, tuple[str, ...]]] = {
    "awslabs.aws-api-mcp-server@1.6.0": {
        "suggest_aws_commands": (),
        CALL_AWS: (),
        # Registered only with ENABLE_AGENT_SCRIPTS; it returns a text plan and calls nothing.
        "get_execution_plan": (),
    },
    "awslabs.cloudtrail-mcp-server@0.1.1": {
        "lookup_events": ("LookupEvents",),
        "lake_query": ("StartQuery", "DescribeQuery", "GetQueryResults"),
        "get_query_status": ("DescribeQuery",),
        "get_query_results": ("GetQueryResults", "DescribeQuery"),
        "list_event_data_stores": ("ListEventDataStores", "GetEventDataStore"),
    },
    "awslabs.billing-cost-management-mcp-server@0.0.44": {
        **{
            name: ("Get*", "List*", "Describe*")
            for name in (
                "aws-pricing",
                "bcm-pricing-calc",
                "list-billing-groups",
                "list-account-associations",
                "list-billing-group-cost-reports",
                "get-billing-group-cost-report",
                "list-custom-line-items",
                "list-custom-line-item-versions",
                "list-resources-associated-to-custom-line-item",
                "list-pricing-rules",
                "list-pricing-plans",
                "list-pricing-rules-for-plan",
                "list-pricing-plans-for-rule",
                "get-billing-transfer-preference",
                "get-billing-preferences",
                "budgets",
                "budget-actions",
                "budget-notifications",
                "budget-performance-history",
                "business-support",
                "get-billing-view",
                "list-billing-views",
                "list-source-views-for-billing-view",
                "get-resource-policy",
                "list-billing-view-segments",
                "compute-optimizer-automation",
                "compute-optimizer",
                "list-cost-allocation-tags",
                "list-cost-allocation-tag-backfill-history",
                "cost-anomaly",
                "cost-anomaly-monitors",
                "describe-cost-category-definition",
                "list-cost-category-definitions",
                "cost-comparison",
                "cost-explorer",
                "cost-optimization",
                "credits",
                "enterprise-support",
                "free-tier-usage",
                "invoicing",
                "procurement-preferences",
                "rec-details",
                "ri-performance",
                "sp-explorer",
                "sp-performance",
            )
        },
        "invoice-units": ("GetInvoiceUnit", "ListInvoiceUnits", "BatchGetInvoiceProfile"),
        # A local SQLite session over earlier tool results; no call to the account.
        "session-sql": (),
        # storage_lens_tools.py: CREATE DATABASE and CREATE EXTERNAL TABLE in Athena, then StartQueryExecution.
        "storage-lens": ("StartQueryExecution", "GetQueryExecution", "GetQueryResults"),
        # sp_purchase_analyzer_tools.py:251.
        "sp-purchase-analyzer": ("StartCommitmentPurchaseAnalysis", "GetCommitmentPurchaseAnalysis"),
        # sp_recommendation_tools.py:375.
        "sp-recommendation": (
            "GetSavingsPlansPurchaseRecommendation",
            "StartSavingsPlansPurchaseRecommendationGeneration",
        ),
    },
}


def _pin(server: dict[str, Any]) -> str:
    args = server.get("args") or []
    return str(args[0]) if len(args) == 1 else " ".join(map(str, args))


def server_problems(servers: dict[str, dict[str, Any]]) -> list[str]:
    """Each mounted server must be one exact, recorded version run by uvx; aws-api must be read-only."""
    problems: list[str] = []
    for name, server in sorted(servers.items()):
        if server.get("disabled"):
            continue
        pin = _pin(server)
        if server.get("command") != "uvx" or not EXACT_PIN.match(pin):
            problems.append(f"{name}: not pinned to an exact version ({server.get('command')} {pin})")
        elif pin not in TOOLS:
            problems.append(f"{name}: {pin} has no recorded tool list, so its tools cannot be judged")
        if (
            pin.startswith("awslabs.aws-api-mcp-server@")
            and (server.get("env") or {}).get("READ_OPERATIONS_ONLY") != "true"
        ):
            problems.append(f"{name}: READ_OPERATIONS_ONLY is not true")
    return problems


def _mounted_servers(agent: dict[str, Any], mcp: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The servers kiro-cli would start: the agent's own map, then the workspace settings when it includes them."""
    servers: dict[str, dict[str, Any]] = {}
    if mcp is not None and agent.get("includeMcpJson"):
        servers.update(mcp.get("mcpServers") or {})
    servers.update(agent.get("mcpServers") or {})
    return servers


def _rules(agent: dict[str, Any], effect: str) -> list[str]:
    rules = (agent.get("permissions") or {}).get("rules") or []
    return [m for r in rules if r.get("capability") == "mcp" and r.get("effect") == effect for m in r.get("match", [])]


def callable_writes(agent: dict[str, Any], mcp: dict[str, Any] | None) -> list[str]:
    """Every ``server/tool`` the agent can call that may call an AWS operation that is not a read.

    A tool can be called when its server is named in ``tools`` (``@server`` or ``@server/tool``), the server is not
    disabled, the tool is not in the server's ``disabledTools``, and no deny rule matches it.
    """
    servers = _mounted_servers(agent, mcp)
    refs = [str(t)[1:] for t in agent.get("tools", []) if str(t).startswith("@")]
    denied = _rules(agent, "deny")
    found: list[str] = []
    for name, server in sorted(servers.items()):
        if server.get("disabled"):
            continue
        tools = TOOLS.get(_pin(server))
        if tools is None:
            continue  # reported by server_problems
        disabled = set(server.get("disabledTools") or [])
        read_only_api = (server.get("env") or {}).get("READ_OPERATIONS_ONLY") == "true"
        for tool, operations in sorted(tools.items()):
            if not any(ref in (name, f"{name}/{tool}") for ref in refs):
                continue
            if tool in disabled or any(fnmatchcase(f"{name}/{tool}", d) for d in denied):
                continue
            writes = [op for op in operations if not READ_OPERATION.match(op)]
            if tool == CALL_AWS and not read_only_api:
                writes.append("any CLI command")
            if writes:
                found.append(f"{name}/{tool}: {', '.join(writes)}")
    return found


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def checkout() -> tuple[dict[str, Any], dict[str, Any]]:
    return _load(CHECKOUT_AGENT), _load(CHECKOUT_MCP)


def test_the_checkout_investigator_can_call_no_tool_that_is_not_a_read(
    checkout: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    assert callable_writes(*checkout) == []


def test_every_server_the_checkout_investigator_mounts_is_pinned_and_aws_api_reads_only(
    checkout: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    agent, mcp = checkout
    assert server_problems(_mounted_servers(agent, mcp)) == []


def test_the_crew_investigator_can_call_no_tool_that_is_not_a_read_and_its_servers_are_pinned() -> None:
    agent = _load(CREW_AGENT)
    assert server_problems(_mounted_servers(agent, None)) == []
    assert callable_writes(agent, None) == []


def test_the_checkout_agent_reads_no_other_server_than_its_settings_declare(
    checkout: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    agent, mcp = checkout
    refs = {str(t)[1:].split("/")[0] for t in agent["tools"] if str(t).startswith("@")}
    assert refs <= set(_mounted_servers(agent, mcp))


# --- The checker itself --------------------------------------------------------------------------------------------

API = {"command": "uvx", "args": ["awslabs.aws-api-mcp-server@1.6.0"], "env": {"READ_OPERATIONS_ONLY": "true"}}
TRAIL = {"command": "uvx", "args": ["awslabs.cloudtrail-mcp-server@0.1.1"], "disabledTools": ["lake_query"]}


def _agent(**servers: dict[str, Any]) -> dict[str, Any]:
    return {"tools": ["read", *(f"@{n}" for n in servers)], "mcpServers": copy.deepcopy(servers)}


def test_regression_lake_query_with_neither_a_deny_rule_nor_disabled_tools_is_a_callable_write() -> None:
    """Bug: the checkout's settings mounted aws-cloudtrail with every tool, so lake_query (StartQuery) was callable."""
    agent = _agent(**{"aws-cloudtrail": {**TRAIL, "disabledTools": []}})
    assert callable_writes(agent, None) == ["aws-cloudtrail/lake_query: StartQuery"]
    agent["permissions"] = {"rules": [{"capability": "mcp", "match": ["aws-cloudtrail/lake_query"], "effect": "deny"}]}
    assert callable_writes(agent, None) == []


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (lambda s: s["aws-api"].update(args=["awslabs.aws-api-mcp-server@latest"]), "not pinned"),
        (lambda s: s["aws-api"].update(args=["awslabs.aws-api-mcp-server"]), "not pinned"),
        (lambda s: s["aws-api"].update(args=["awslabs.aws-api-mcp-server@1.7.0"]), "no recorded tool list"),
        (lambda s: s["aws-api"]["env"].pop("READ_OPERATIONS_ONLY"), "READ_OPERATIONS_ONLY is not true"),
        (lambda s: s["aws-api"]["env"].update(READ_OPERATIONS_ONLY="false"), "READ_OPERATIONS_ONLY is not true"),
        (lambda s: s["aws-cloudtrail"].update(command="npx"), "not pinned"),
    ],
)
def test_the_checker_refuses_an_unpinned_unknown_or_writable_server(edit: Any, problem: str) -> None:
    servers: dict[str, dict[str, Any]] = copy.deepcopy({"aws-api": API, "aws-cloudtrail": TRAIL})
    edit(servers)
    assert any(problem in p for p in server_problems(servers))


def test_the_checker_sees_call_aws_without_read_only_mode_as_a_write() -> None:
    agent = _agent(**{"aws-api": {**API, "env": {}}})
    assert callable_writes(agent, None) == ["aws-api/call_aws: any CLI command"]


def test_the_checker_sees_each_billing_tool_that_starts_a_query_or_analysis() -> None:
    billing = {"command": "uvx", "args": ["awslabs.billing-cost-management-mcp-server@0.0.44"]}
    found = callable_writes(_agent(**{"aws-billing": billing}), None)
    assert [f.split(":")[0] for f in found] == [
        "aws-billing/sp-purchase-analyzer",
        "aws-billing/sp-recommendation",
        "aws-billing/storage-lens",
    ]


def test_a_tool_ref_to_one_tool_mounts_only_that_tool() -> None:
    agent = _agent(**{"aws-cloudtrail": {**TRAIL, "disabledTools": []}})
    agent["tools"] = ["@aws-cloudtrail/lookup_events"]
    assert callable_writes(agent, None) == []


def test_a_server_from_the_settings_counts_only_when_the_agent_includes_them() -> None:
    mcp = {"mcpServers": {"aws-cloudtrail": {**TRAIL, "disabledTools": []}}}
    agent: dict[str, Any] = {"tools": ["@aws-cloudtrail"], "includeMcpJson": False}
    assert callable_writes(agent, mcp) == []
    agent["includeMcpJson"] = True
    assert callable_writes(agent, mcp) == ["aws-cloudtrail/lake_query: StartQuery"]
