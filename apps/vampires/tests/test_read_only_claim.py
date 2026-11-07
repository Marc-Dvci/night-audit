"""The read-only claim, checked against the deployment template and the connector code (Vampires Req 8.4, 8.5).

The claim: the nightly role writes one thing, ``s3:PutObject`` on its own runs bucket under ``nights/*``, to store its
own run. Beside it, each function role may write its own log lines to its own log group (``logs:CreateLogStream`` and
``logs:PutLogEvents``), because a function that cannot log fails without a trace. Connectors make no write call.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "deploy" / "stack.yaml"
READ_ACTION = re.compile(r"^[A-Za-z0-9-]+:(Get|List|Describe|Lookup)[A-Za-z0-9*]*$")

#: The only writes each role may hold: (action, resource as written in the template). Nothing else.
ALLOWED_WRITES: dict[str, set[tuple[str, str]]] = {
    "NightlyRole": {
        ("s3:PutObject", "${RunsBucket.Arn}/nights/*"),
        ("logs:CreateLogStream", "${NightlyLogs.Arn}:*"),
        ("logs:PutLogEvents", "${NightlyLogs.Arn}:*"),
    },
    "WebRole": {
        ("logs:CreateLogStream", "${WebLogs.Arn}:*"),
        ("logs:PutLogEvents", "${WebLogs.Arn}:*"),
    },
    "SchedulerRole": {("lambda:InvokeFunction", "NightlyFunction.Arn")},
}
#: Managed policies a role may attach. ReadOnlyAccess is AWS's own definition of read-only; this test cannot open it.
ALLOWED_MANAGED: dict[str, set[str]] = {
    "NightlyRole": {"arn:aws:iam::aws:policy/ReadOnlyAccess"},
    "WebRole": set(),
    "SchedulerRole": set(),
}


class _Template(yaml.SafeLoader):
    """CloudFormation short tags (``!Sub``, ``!Ref``, ``!GetAtt``) read as plain values."""


def _tag(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)  # type: ignore[arg-type]


_Template.add_multi_constructor("!", _tag)


def _roles() -> dict[str, dict[str, Any]]:
    template = yaml.load(STACK.read_text(encoding="utf-8"), Loader=_Template)  # noqa: S506 - the loader is SafeLoader
    return {n: r["Properties"] for n, r in template["Resources"].items() if r["Type"] == "AWS::IAM::Role"}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def writes_of(properties: dict[str, Any]) -> tuple[set[tuple[str, str]], list[str]]:
    """Every (action, resource) an Allow statement grants that is not a read, and the problems with the statements."""
    writes: set[tuple[str, str]] = set()
    problems: list[str] = []
    for policy in properties.get("Policies", []):
        for statement in policy["PolicyDocument"]["Statement"]:
            if statement.get("Effect") != "Allow":
                continue
            if "NotAction" in statement or "NotResource" in statement:
                problems.append(f"{policy['PolicyName']}: NotAction or NotResource widens the grant")
                continue
            for action in _as_list(statement["Action"]):
                if not READ_ACTION.match(action):
                    for resource in _as_list(statement["Resource"]):
                        writes.add((action, resource))
    return writes, problems


def test_the_template_has_the_roles_this_test_knows() -> None:
    assert set(_roles()) == set(ALLOWED_WRITES)


@pytest.mark.parametrize("role", sorted(ALLOWED_WRITES))
def test_a_role_can_write_only_what_the_claim_names(role: str) -> None:
    writes, problems = writes_of(_roles()[role])
    assert problems == []
    assert writes == ALLOWED_WRITES[role], f"{role} holds writes beyond the claim: {writes - ALLOWED_WRITES[role]}"


@pytest.mark.parametrize("role", sorted(ALLOWED_MANAGED))
def test_a_role_attaches_only_the_managed_policies_the_claim_names(role: str) -> None:
    assert set(_roles()[role].get("ManagedPolicyArns", [])) == ALLOWED_MANAGED[role]


def test_the_nightly_role_writes_to_s3_only_under_nights() -> None:
    writes, _ = writes_of(_roles()["NightlyRole"])
    assert {r for a, r in writes if a.startswith("s3:")} == {"${RunsBucket.Arn}/nights/*"}


def test_a_widened_policy_is_seen_as_a_write() -> None:
    """The checker itself: each of these grants must show up as a write."""
    for action in ("s3:*", "*:*", "s3:PutObject*", "ec2:TerminateInstances", "iam:PassRole", "s3:DeleteObject"):
        properties = {
            "Policies": [
                {
                    "PolicyName": "p",
                    "PolicyDocument": {"Statement": [{"Effect": "Allow", "Action": [action], "Resource": "*"}]},
                }
            ]
        }
        assert writes_of(properties)[0] == {(action, "*")}, action
    reads = {
        "Policies": [
            {
                "PolicyName": "p",
                "PolicyDocument": {
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": ["s3:GetObject", "ec2:Describe*", "cloudtrail:LookupEvents", "ce:Get*"],
                            "Resource": "*",
                        }
                    ]
                },
            }
        ]
    }
    assert writes_of(reads)[0] == set()


# --- Connectors make no write call -----------------------------------------------------------------------------------

READ_PREFIXES = ("describe_", "list_", "get_", "lookup_")
WRITE_PREFIXES = (
    "put_",
    "delete_",
    "create_",
    "update_",
    "terminate_",
    "modify_",
    "start_",
    "stop_",
    "run_",
    "attach_",
    "detach_",
    "tag_",
    "untag_",
    "invoke",
    "upload_",
    "copy_",
    "send_",
    "publish_",
    "set_",
    "add_",
    "remove_",
    "register_",
    "deregister_",
    "reboot_",
    "release_",
    "allocate_",
    "associate_",
    "disassociate_",
    "enable_",
    "disable_",
    "authorize_",
    "revoke_",
    "restore_",
)


def _talks_to_aws(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return "boto3" in text or ".client(" in text or "get_paginator" in text


#: Every module of an app or of the skeleton's connectors that can reach AWS.
_SKELETON_CONNECTORS = ROOT / "skeleton" / "src" / "nightaudit" / "connectors.py"
CONNECTOR_SOURCES = [
    p for p in [*sorted((ROOT / "apps").glob("*/src/**/*.py")), _SKELETON_CONNECTORS] if _talks_to_aws(p)
]


def aws_operations(source: str) -> list[tuple[int, str]]:
    """Every AWS operation a module names: methods called on a client, and operations passed to a paginator."""
    tree = ast.parse(source)
    clients: set[str] = set()
    found: list[tuple[int, str]] = []

    def is_client_call(node: ast.AST) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "client"

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and is_client_call(node.value):
            clients.update(t.id for t in node.targets if isinstance(t, ast.Name))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            receiver = func.value
            on_client = (isinstance(receiver, ast.Name) and receiver.id in clients) or is_client_call(receiver)
            if on_client or func.attr.startswith(WRITE_PREFIXES):
                found.append((node.lineno, func.attr))
            if func.attr == "get_paginator" and node.args and isinstance(node.args[0], ast.Constant):
                found.append((node.lineno, str(node.args[0].value)))
        if isinstance(func, ast.Name) and func.id == "_paginate" and len(node.args) > 1:
            if isinstance(node.args[1], ast.Constant):
                found.append((node.lineno, str(node.args[1].value)))
    return found


def not_reads(source: str) -> list[tuple[int, str]]:
    return [
        (line, op)
        for line, op in aws_operations(source)
        if not op.startswith(READ_PREFIXES) and op not in {"client", "paginate"}
    ]


@pytest.mark.parametrize("path", CONNECTOR_SOURCES, ids=lambda p: p.name)
def test_a_connector_module_calls_no_aws_operation_that_is_not_a_read(path: Path) -> None:
    assert not_reads(path.read_text(encoding="utf-8")) == []


def test_the_vampires_connectors_are_among_the_modules_scanned() -> None:
    names = {p.name for p in CONNECTOR_SOURCES}
    assert "aws.py" in names
    assert {op for _, op in aws_operations((ROOT / "apps/vampires/src/vampires/aws.py").read_text("utf-8"))} >= {
        "describe_instances",
        "list_buckets",
        "lookup_events",
        "get_object",
        "list_objects_v2",
    }


@pytest.mark.parametrize(
    "call",
    [
        's3.put_object(Bucket="b", Key="k", Body=b"")',
        'ec2.terminate_instances(InstanceIds=["i-1"])',
        'boto3.client("s3").delete_object(Bucket="b", Key="k")',
        '_paginate(ec2, "modify_volume", "Volumes")',
        'client.get_paginator("create_snapshot")',
        's3.upload_file("a", "b", "c")',
    ],
)
def test_the_scan_catches_a_write_call(call: str) -> None:
    source = f'import boto3\ns3 = boto3.client("s3")\nec2 = boto3.client("ec2")\n{call}\n'
    assert not_reads(source) != []
