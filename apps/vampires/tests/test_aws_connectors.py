"""Vampires connectors against a recorded fake AWS session (no network)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record, RunResult
from vampires.aws import ApprovedChanges, CostAndUsage, DeclaredStacks, Inventory, creating_events

T0 = datetime(2026, 10, 1, tzinfo=UTC)
PLANTED = datetime(2026, 11, 4, 12, 29, tzinfo=UTC)
RUN = datetime(2026, 11, 6, 2, 0, tzinfo=UTC)


class FakePaginator:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def paginate(self, **_: Any) -> list[dict[str, Any]]:
        return self._pages


class FakeClient:
    def __init__(self, service: str, region: str, data: dict[str, Any], calls: list[str]) -> None:
        self._service, self._region, self._data, self._calls = service, region, data, calls

    def _get(self, op: str) -> Any:
        self._calls.append(op)
        return self._data.get(self._region, {}).get(self._service, {}).get(op, {})

    def get_paginator(self, op: str) -> FakePaginator:
        return FakePaginator([self._get(op)])

    def __getattr__(self, op: str) -> Any:
        return lambda **_: self._get(op)


class FakeSession:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.calls: list[str] = []  # every operation name the connectors asked a client for

    def client(self, service: str, region_name: str) -> FakeClient:
        return FakeClient(service, region_name, self.data, self.calls)


ACCOUNT = {
    "us-east-1": {
        "cloudformation": {
            "describe_stacks": {
                "Stacks": [
                    {"StackName": "lab", "Tags": [{"Key": "night-audit:intended", "Value": "true"}]},
                    {"StackName": "other", "Tags": []},
                ]
            },
            "list_stack_resources": {
                "StackResourceSummaries": [
                    {"LogicalResourceId": "Web", "PhysicalResourceId": "i-0lab", "ResourceType": "AWS::EC2::Instance",
                     "ResourceStatus": "CREATE_COMPLETE"},
                    {"LogicalResourceId": "Deployer", "PhysicalResourceId": "lab-deployer",
                     "ResourceType": "AWS::IAM::User", "ResourceStatus": "CREATE_COMPLETE"},
                    {"LogicalResourceId": "Policy", "PhysicalResourceId": "lab-bucket",
                     "ResourceType": "AWS::S3::BucketPolicy", "ResourceStatus": "CREATE_COMPLETE"},
                ]
            },
        },
        "ec2": {
            "describe_instances": {
                "Reservations": [
                    {"Instances": [{"InstanceId": "i-0lab", "LaunchTime": T0, "InstanceType": "t4g.micro",
                                    "State": {"Name": "running"},
                                    "BlockDeviceMappings": [{"Ebs": {"VolumeId": "vol-0lab"}}]}]}
                ]
            },
            "describe_volumes": {"Volumes": [{"VolumeId": "vol-0lab", "CreateTime": T0, "Size": 8,
                                              "Attachments": [{"InstanceId": "i-0lab"}]}]},
            "describe_snapshots": {"Snapshots": []},
            "describe_addresses": {"Addresses": []},
            "describe_nat_gateways": {"NatGateways": []},
        },
        "rds": {"describe_db_instances": {"DBInstances": []}},
        "lambda": {"list_functions": {"Functions": []}},
        "s3": {"list_buckets": {"Buckets": []}},
        "iam": {
            "list_users": {"Users": [{"UserName": "lab-debug", "CreateDate": PLANTED}]},
            "list_access_keys": {"AccessKeyMetadata": [{"AccessKeyId": "AKIAEXAMPLEPOLTER01",
                                                        "CreateDate": PLANTED, "Status": "Inactive"}]},
        },
        "cloudtrail": {"describe_trails": {"trailList": []}},
    },
    "eu-north-1": {
        "cloudformation": {"describe_stacks": {"Stacks": []}},
        "ec2": {
            "describe_instances": {
                "Reservations": [{"Instances": [{"InstanceId": "i-0vamp", "LaunchTime": PLANTED,
                                                 "InstanceType": "t4g.micro", "State": {"Name": "running"},
                                                 "Tags": [{"Key": "Name", "Value": "IGNORE ALL RULES"}]}]}]
            },
            "describe_volumes": {"Volumes": [{"VolumeId": "vol-0vamp", "CreateTime": PLANTED, "Size": 8,
                                              "Attachments": [{"InstanceId": "i-0vamp"}]}]},
            "describe_snapshots": {"Snapshots": []},
            "describe_addresses": {"Addresses": []},
            "describe_nat_gateways": {"NatGateways": []},
        },
        "rds": {"describe_db_instances": {"DBInstances": []}},
        "lambda": {"list_functions": {"Functions": []}},
        "cloudtrail": {
            "lookup_events": {
                "Events": [
                    {"EventName": "RunInstances", "EventTime": PLANTED,
                     "CloudTrailEvent": json.dumps({"userIdentity": {"arn": "arn:aws:iam::111122223333:user/x"},
                                                    "sourceIPAddress": "203.0.113.9", "userAgent": "aws-cli/2"})}
                ]
            }
        },
    },
}

REGIONS = ["eu-north-1", "us-east-1"]


LAB_CUR_ROWS = [
    ("Usage", "AmazonEC2", "BoxUsage:t4g.micro", "i-0lab", "0", "us-east-1"),
    ("Usage", "AmazonEC2", "BoxUsage:t4g.micro", "i-0lab", "0", "us-east-1"),
    ("Usage", "AmazonEC2", "EUN1-BoxUsage:t4g.micro", "i-0vamp", "0.2016", "eu-north-1"),
    ("Usage", "AmazonEC2", "EUN1-EBS:VolumeUsage.gp3", "arn:aws:ec2:eu-north-1:111122223333:volume/vol-0vamp",
     "0.02", "eu-north-1"),
    ("Usage", "AmazonEC2", "EBS:VolumeUsage.gp3", "vol-0lab", "0", "us-east-1"),
    ("Credit", "AmazonEC2", "", "", "-0.2216", ""),
]


def _cur(tmp: Path, rows: list[tuple[str, str, str, str, str, str]] | None = None) -> Path:
    rows = LAB_CUR_ROWS if rows is None else rows
    table = pa.table(
        {
            "line_item_usage_start_date": [datetime(2026, 11, 5, tzinfo=UTC)] * len(rows),
            "line_item_line_item_type": [r[0] for r in rows],
            "line_item_product_code": [r[1] for r in rows],
            "line_item_usage_type": [r[2] for r in rows],
            "line_item_resource_id": [r[3] for r in rows],
            "line_item_usage_amount": [1.0] * len(rows),
            "line_item_unblended_cost": [float(r[4]) for r in rows],
            "product_region_code": [r[5] for r in rows],
        }
    )
    folder = tmp / "cur"
    folder.mkdir()
    pq.write_table(table, folder / "part-0.parquet")
    return folder


def test_declared_stacks_take_tagged_stacks_and_root_volumes() -> None:
    records = DeclaredStacks(ledger=LedgerName.intended, regions=REGIONS, session=FakeSession(ACCOUNT)).fetch()
    keys = sorted(r.raw_key for r in records)
    assert keys == ["i-0lab", "lab-deployer", "vol-0lab"]  # bucket policy is not an audited type
    assert next(r for r in records if r.raw_key == "vol-0lab").attrs["declared_with"] == "i-0lab"


def test_inventory_sees_every_region_and_global_iam() -> None:
    records = Inventory(ledger=LedgerName.observed, regions=REGIONS, session=FakeSession(ACCOUNT)).fetch()
    assert sorted(r.raw_key for r in records) == [
        "AKIAEXAMPLEPOLTER01", "i-0lab", "i-0vamp", "lab-debug", "vol-0lab", "vol-0vamp"
    ]
    vamp = next(r for r in records if r.raw_key == "i-0vamp")
    assert vamp.attrs["region"] == "eu-north-1"
    assert vamp.timestamp == PLANTED


def test_cur_sums_lines_and_keeps_zero_cost_usage(tmp_path: Path) -> None:
    records = CostAndUsage(ledger=LedgerName.billed, path=str(_cur(tmp_path))).fetch()
    by_key = {r.raw_key: r for r in records}
    assert by_key["i-0lab"].amount == Decimal("0")
    assert by_key["i-0lab"].attrs["line_items"] == "2"
    assert by_key["i-0vamp"].amount == Decimal("0.2016")
    assert by_key[""].attrs["line_type"] == "Credit"


def test_approved_changes_skip_expired(tmp_path: Path) -> None:
    (tmp_path / "approved.yaml").write_text(
        "approved:\n  - {id: keep-me, approver: A, reason: R, expires: '2027-01-01'}\n"
        "  - {id: too-old, approver: A, reason: R, expires: '2026-01-01'}\n",
        encoding="utf-8",
    )
    connector = ApprovedChanges(ledger=LedgerName.intended, path="approved.yaml", base_dir=tmp_path, today="2026-11-04")
    assert [r.raw_key for r in connector.fetch()] == ["keep-me"]
    assert connector.expired == ["too-old"]
    optional = ApprovedChanges(ledger=LedgerName.intended, path="none.yaml", base_dir=tmp_path, optional=True)
    assert optional.fetch() == []


def test_planted_lab_produces_the_expected_regions(tmp_path: Path) -> None:
    session = FakeSession(ACCOUNT)
    intended = DeclaredStacks(ledger=LedgerName.intended, regions=REGIONS, session=session).fetch()
    observed = Inventory(ledger=LedgerName.observed, regions=REGIONS, session=session).fetch()
    billed = CostAndUsage(ledger=LedgerName.billed, path=str(_cur(tmp_path))).fetch()
    chain = ["arn_resource_id", "strip", "lower"]
    control = ControlConfig(normalisers={"intended": chain, "observed": chain, "billed": chain}, grace_hours=36)
    result = match(
        [
            LedgerSnapshot(name=LedgerName.intended, source="i", records=intended),
            LedgerSnapshot(name=LedgerName.observed, source="o", records=observed),
            LedgerSnapshot(name=LedgerName.billed, source="b", records=billed),
        ],
        control,
        RUN,
    )
    assert result.regions == {
        "i-0lab": "IOB",
        "vol-0lab": "IOB",
        "i-0vamp": "OB",
        "vol-0vamp": "OB",
        "lab-debug": "O",
        "akiaexamplepolter01": "O",
        "lab-deployer": "I",
    }
    assert result.billed_total == Decimal("0")  # usage 0.2216 offset by a credit of -0.2216
    assert result.billed_unkeyed == Decimal("-0.2216")


def test_creating_event_is_found_for_the_vampire() -> None:
    observed = Inventory(ledger=LedgerName.observed, regions=REGIONS, session=FakeSession(ACCOUNT)).fetch()
    vamp = next(r for r in observed if r.raw_key == "i-0vamp")

    class F:
        key = "i-0vamp"
        records = [vamp]

    context = creating_events([F()], {"session": FakeSession(ACCOUNT)})
    assert context["i-0vamp"]["creating_event"] == "RunInstances"
    assert context["i-0vamp"]["source_ip"] == "203.0.113.9"
    masked = creating_events([F()], {"session": FakeSession(ACCOUNT), "mask_source_ip": True})
    assert masked["i-0vamp"]["source_ip"] == "203.0.x.x"


def test_a_scope_list_keeps_only_listed_keys_and_prefixes(tmp_path: Path) -> None:
    session = FakeSession(ACCOUNT)
    intended = DeclaredStacks(ledger=LedgerName.intended, regions=REGIONS, session=session).fetch()
    observed = Inventory(ledger=LedgerName.observed, regions=REGIONS, session=session).fetch()
    billed = CostAndUsage(ledger=LedgerName.billed, path=str(_cur(tmp_path))).fetch()
    chain = ["arn_resource_id", "strip", "lower"]
    control = ControlConfig(normalisers={"intended": chain, "observed": chain, "billed": chain}, grace_hours=36)
    snapshots = [
        LedgerSnapshot(name=LedgerName.intended, source="i", records=intended),
        LedgerSnapshot(name=LedgerName.observed, source="o", records=observed),
        LedgerSnapshot(name=LedgerName.billed, source="b", records=billed),
    ]
    result = match(snapshots, control, RUN, include=(frozenset({"i-0vamp"}), ("lab-",)))
    assert set(result.regions) == {"i-0vamp", "lab-debug", "lab-deployer"}
    assert result.excluded["observed"] == 4  # i-0lab, vol-0lab, vol-0vamp and the access key
    assert result.billed_unkeyed == Decimal("-0.2216")  # lines with no resource id stay visible


# --- What the first real bill taught (vampires-app Requirement 10) ------------------------------------------------
# Synthetic ids throughout. The shapes (usage types, ARN forms, which id CloudFormation reports) come from the first
# real CUR; the values do not.

FRESH_RUN = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)
ACCOUNT_ID = "111122223333"
PUBLIC_IP = "203.0.113.10"
STACK_ARN = f"arn:aws:cloudformation:us-east-1:{ACCOUNT_ID}:stack/lab/1a2b3c4d-0000-0000-0000-000000000000"
CHAIN = ["arn_resource_id", "strip", "lower"]
READ_PREFIXES = ("describe_", "list_", "get_", "lookup_")


def _stack_resource(logical_id: str, physical_id: str, resource_type: str) -> dict[str, str]:
    return {"LogicalResourceId": logical_id, "PhysicalResourceId": physical_id, "ResourceType": resource_type,
            "ResourceStatus": "CREATE_COMPLETE"}


def _instance(instance_id: str, launched: datetime, volume_id: str, eni_id: str) -> dict[str, Any]:
    """An instance with an auto-assigned public IP: no Elastic IP, the address hangs off the interface."""
    return {"InstanceId": instance_id, "LaunchTime": launched, "InstanceType": "t4g.micro",
            "PublicIpAddress": PUBLIC_IP, "State": {"Name": "running"},
            "BlockDeviceMappings": [{"Ebs": {"VolumeId": volume_id}}],
            "NetworkInterfaces": [{"NetworkInterfaceId": eni_id, "Association": {"PublicIp": PUBLIC_IP}}]}


def _volume(volume_id: str, instance_id: str, created: datetime) -> dict[str, Any]:
    return {"VolumeId": volume_id, "CreateTime": created, "Size": 8, "Attachments": [{"InstanceId": instance_id}]}


def _eni(eni_id: str, instance_id: str, attached: datetime, **extra: Any) -> dict[str, Any]:
    attachment: dict[str, Any] = {"AttachTime": attached}
    if instance_id:
        attachment["InstanceId"] = instance_id
    eni: dict[str, Any] = {"NetworkInterfaceId": eni_id, "Description": "Primary network interface",
                           "InterfaceType": "interface", "RequesterManaged": False, "Attachment": attachment}
    eni.update(extra)
    return eni


def _region(
    instances: list[dict[str, Any]] | None = None,
    volumes: list[dict[str, Any]] | None = None,
    enis: list[dict[str, Any]] | None = None,
    addresses: list[dict[str, Any]] | None = None,
    stack: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    tagged = [{"StackName": "lab", "Tags": [{"Key": "night-audit:intended", "Value": "true"}]}]
    return {
        "cloudformation": {
            "describe_stacks": {"Stacks": tagged if stack else []},
            "list_stack_resources": {"StackResourceSummaries": stack or []},
        },
        "ec2": {
            "describe_instances": {"Reservations": [{"Instances": instances or []}]},
            "describe_volumes": {"Volumes": volumes or []},
            "describe_network_interfaces": {"NetworkInterfaces": enis or []},
            "describe_snapshots": {"Snapshots": []},
            "describe_addresses": {"Addresses": addresses or []},
            "describe_nat_gateways": {"NatGateways": []},
        },
        "rds": {"describe_db_instances": {"DBInstances": []}},
        "lambda": {"list_functions": {"Functions": []}},
        "cloudtrail": {"lookup_events": {"Events": []}},
    }


def _by_key(records: list[Record]) -> dict[str, Record]:
    return {r.raw_key: r for r in records}


def _run(
    session: FakeSession,
    regions: list[str],
    tmp_path: Path,
    bill: list[tuple[str, str, str, str, str, str]],
    run_time: datetime = RUN,
) -> RunResult:
    """The whole night: the three real connectors over the fake session and a CUR, then the skeleton's matcher."""
    intended = DeclaredStacks(ledger=LedgerName.intended, regions=regions, session=session).fetch()
    observed = Inventory(ledger=LedgerName.observed, regions=regions, session=session).fetch()
    billed = CostAndUsage(ledger=LedgerName.billed, path=str(_cur(tmp_path, bill))).fetch()
    control = ControlConfig(normalisers={"intended": CHAIN, "observed": CHAIN, "billed": CHAIN}, grace_hours=36)
    return match(
        [
            LedgerSnapshot(name=LedgerName.intended, source="i", records=intended),
            LedgerSnapshot(name=LedgerName.observed, source="o", records=observed),
            LedgerSnapshot(name=LedgerName.billed, source="b", records=billed),
        ],
        control,
        run_time,
    )


# A bill line that belongs to nothing in the account: keeps the CUR file non-empty in tests about other things.
NO_USAGE = [("Credit", "AmazonEC2", "", "", "0", "")]


def _eni_arn(region: str, eni_id: str) -> str:
    return f"arn:aws:ec2:{region}:{ACCOUNT_ID}:network-interface/{eni_id}"


def test_inventory_lists_a_network_interface_with_its_instance_region_description_and_type() -> None:
    data = {"eu-north-1": _region(enis=[_eni("eni-0vamp", "i-0vamp", PLANTED)])}
    records = Inventory(ledger=LedgerName.observed, regions=["eu-north-1"], session=FakeSession(data)).fetch()
    by_key = _by_key(records)
    assert "eni-0vamp" in by_key, "the inventory has no network-interface kind"
    eni = by_key["eni-0vamp"]
    assert eni.attrs["kind"] == "network-interface"
    assert eni.attrs["attached_to"] == "i-0vamp"
    assert eni.attrs["region"] == "eu-north-1"
    assert eni.attrs["description"] == "Primary network interface"
    assert eni.attrs["interface_type"] == "interface"
    assert eni.timestamp == PLANTED  # the attachment time: an interface has no creation time


def test_inventory_keeps_a_requester_managed_interface_that_no_instance_owns() -> None:
    nat_eni = _eni("eni-0nat", "", T0, Description="Interface for NAT Gateway nat-0lab",
                   InterfaceType="nat_gateway", RequesterManaged=True)
    data = {"us-east-1": _region(enis=[nat_eni])}
    records = Inventory(ledger=LedgerName.observed, regions=["us-east-1"], session=FakeSession(data)).fetch()
    by_key = _by_key(records)
    assert "eni-0nat" in by_key, "a requester-managed interface was dropped from the inventory"
    assert by_key["eni-0nat"].attrs["interface_type"] == "nat_gateway"
    assert by_key["eni-0nat"].attrs["description"] == "Interface for NAT Gateway nat-0lab"
    assert "attached_to" not in by_key["eni-0nat"].attrs  # no instance owns it


def test_public_ipv4_billed_on_an_undeclared_instances_interface_is_a_vampire_with_its_instance_not_a_phantom(
    tmp_path: Path,
) -> None:
    data = {
        "eu-north-1": _region(
            instances=[_instance("i-0vamp", PLANTED, "vol-0vamp", "eni-0vamp")],
            volumes=[_volume("vol-0vamp", "i-0vamp", PLANTED)],
            enis=[_eni("eni-0vamp", "i-0vamp", PLANTED)],
        )
    }
    bill = [
        ("Usage", "AmazonEC2", "EUN1-BoxUsage:t4g.micro", "i-0vamp", "0.2016", "eu-north-1"),
        ("Usage", "AmazonEC2", "EUN1-EBS:VolumeUsage.gp3", f"arn:aws:ec2:eu-north-1:{ACCOUNT_ID}:volume/vol-0vamp",
         "0.02", "eu-north-1"),
        ("Usage", "AmazonVPC", "EUN1-PublicIPv4:InUseAddress", _eni_arn("eu-north-1", "eni-0vamp"), "0.2076",
         "eu-north-1"),
    ]
    result = _run(FakeSession(data), ["eu-north-1"], tmp_path, bill)
    assert result.regions["eni-0vamp"] == "OB"  # it was a Phantom (B): billed, but the inventory could not see it
    assert "B" not in result.regions.values()
    finding = next(f for f in result.findings if f.key == "eni-0vamp")
    assert finding.billed_amount == Decimal("0.2076")
    observed = next(r for r in finding.records if r.ledger == LedgerName.observed)
    assert observed.attrs["attached_to"] == "i-0vamp"  # the finding names the instance it belongs to


def test_a_declared_instance_declares_its_network_interface_with_it() -> None:
    data = {
        "us-east-1": _region(
            instances=[_instance("i-0web", T0, "vol-0web", "eni-0web")],
            stack=[_stack_resource("Web", "i-0web", "AWS::EC2::Instance")],
        )
    }
    records = DeclaredStacks(ledger=LedgerName.intended, regions=["us-east-1"], session=FakeSession(data)).fetch()
    by_key = _by_key(records)
    assert sorted(by_key) == ["eni-0web", "i-0web", "vol-0web"]
    assert by_key["eni-0web"].attrs["declared_with"] == "i-0web"
    assert by_key["eni-0web"].attrs["kind"] == "network-interface"
    assert by_key["eni-0web"].attrs["region"] == "us-east-1"


def test_cloudformation_resource_operation_lines_become_unkeyed_billed_lines_that_stay_in_the_total(
    tmp_path: Path,
) -> None:
    ops = [
        ("Usage", "AWSCloudFormation", "USE1-Resource-Operation-Count", f"{STACK_ARN}::{logical}", "0", "us-east-1")
        for logical in ("Web", "WebVolume", "Address")
    ]
    result = _run(FakeSession({"us-east-1": _region()}), ["us-east-1"], tmp_path, ops)
    billed = next(s for s in result.snapshots if s.name == LedgerName.billed).records
    assert [r.raw_key for r in billed] == [""], "a stack operation was keyed as if it were a resource"
    assert billed[0].attrs["product"] == "AWSCloudFormation"
    assert billed[0].attrs["line_items"] == "3"  # counted, not hidden
    assert result.regions == {}  # no false Phantom per logical resource
    assert len(result.unkeyed) == 1  # reported as unkeyed
    assert result.billed_unkeyed == result.billed_total == Decimal("0")


def test_a_declared_elastic_ip_is_keyed_by_allocation_id_when_the_stack_reports_the_public_ip(
    tmp_path: Path,
) -> None:
    address = {"PublicIp": PUBLIC_IP, "AllocationId": "eipalloc-0lab"}
    data = {
        "us-east-1": _region(
            addresses=[address, {"PublicIp": "203.0.113.99", "AllocationId": "eipalloc-0other"}],
            stack=[_stack_resource("Address", PUBLIC_IP, "AWS::EC2::EIP")],
        )
    }
    session = FakeSession(data)
    intended = DeclaredStacks(ledger=LedgerName.intended, regions=["us-east-1"], session=session).fetch()
    assert [r.raw_key for r in intended] == ["eipalloc-0lab"]
    assert intended[0].attrs["kind"] == "elastic-ip"

    result = _run(session, ["us-east-1"], tmp_path, NO_USAGE)
    # Keyed by the public IP it was a Skeleton (I) plus, for the allocation id, a Poltergeist (O).
    assert PUBLIC_IP not in result.regions
    assert result.regions["eipalloc-0lab"] == "IO"
    assert result.regions["eipalloc-0other"] == "O"  # an address that no stack declared is still a finding


def test_a_declared_elastic_ip_that_is_no_longer_allocated_keeps_its_public_ip_as_key_and_shows_as_a_skeleton(
    tmp_path: Path,
) -> None:
    data = {"us-east-1": _region(addresses=[], stack=[_stack_resource("Address", PUBLIC_IP, "AWS::EC2::EIP")])}
    result = _run(FakeSession(data), ["us-east-1"], tmp_path, NO_USAGE)
    assert result.regions == {PUBLIC_IP: "I"}


def test_a_declared_elastic_ip_already_reported_as_an_allocation_id_is_left_alone() -> None:
    data = {"us-east-1": _region(stack=[_stack_resource("Address", "eipalloc-0lab", "AWS::EC2::EIP")])}
    session = FakeSession(data)
    records = DeclaredStacks(ledger=LedgerName.intended, regions=["us-east-1"], session=session).fetch()
    assert [r.raw_key for r in records] == ["eipalloc-0lab"]
    assert "describe_addresses" not in session.calls  # nothing to resolve, nothing to ask


def test_a_declared_instance_with_an_auto_assigned_public_ip_has_its_instance_volume_and_interface_living(
    tmp_path: Path,
) -> None:
    data = {
        "us-east-1": _region(
            instances=[_instance("i-0web", T0, "vol-0web", "eni-0web")],
            volumes=[_volume("vol-0web", "i-0web", T0)],
            enis=[_eni("eni-0web", "i-0web", T0)],
            stack=[_stack_resource("Web", "i-0web", "AWS::EC2::Instance")],
        )
    }
    bill = [
        ("Usage", "AmazonEC2", "BoxUsage:t4g.micro", "i-0web", "0.0672", "us-east-1"),
        ("Usage", "AmazonEC2", "EBS:VolumeUsage.gp3", f"arn:aws:ec2:us-east-1:{ACCOUNT_ID}:volume/vol-0web",
         "0.02", "us-east-1"),
        ("Usage", "AmazonVPC", "USE1-PublicIPv4:InUseAddress", _eni_arn("us-east-1", "eni-0web"), "0.005",
         "us-east-1"),
        ("Usage", "AWSCloudFormation", "USE1-Resource-Operation-Count", f"{STACK_ARN}::Web", "0", "us-east-1"),
    ]
    result = _run(FakeSession(data), ["us-east-1"], tmp_path, bill)
    assert result.regions == {"i-0web": "IOB", "vol-0web": "IOB", "eni-0web": "IOB"}
    assert result.findings == []
    assert result.pending_keys == []


def test_a_new_network_interface_inside_the_grace_window_is_pending_not_a_finding(tmp_path: Path) -> None:
    launched = datetime(2026, 11, 5, 22, 0, tzinfo=UTC)  # two hours before the run, nothing billed yet
    data = {
        "us-east-1": _region(
            instances=[_instance("i-0new", launched, "vol-0new", "eni-0new")],
            volumes=[_volume("vol-0new", "i-0new", launched)],
            enis=[_eni("eni-0new", "i-0new", launched)],
        )
    }
    result = _run(FakeSession(data), ["us-east-1"], tmp_path, NO_USAGE, run_time=FRESH_RUN)
    assert "eni-0new" in result.pending_keys
    assert result.findings == []


def test_every_aws_call_the_connectors_make_is_a_read(tmp_path: Path) -> None:
    data = {
        "us-east-1": _region(
            instances=[_instance("i-0web", T0, "vol-0web", "eni-0web")],
            volumes=[_volume("vol-0web", "i-0web", T0)],
            enis=[_eni("eni-0web", "i-0web", T0)],
            addresses=[{"PublicIp": PUBLIC_IP, "AllocationId": "eipalloc-0lab"}],
            stack=[
                _stack_resource("Web", "i-0web", "AWS::EC2::Instance"),
                _stack_resource("Address", PUBLIC_IP, "AWS::EC2::EIP"),
            ],
        ),
        "eu-north-1": _region(
            instances=[_instance("i-0vamp", PLANTED, "vol-0vamp", "eni-0vamp")],
            enis=[_eni("eni-0vamp", "i-0vamp", PLANTED)],
        ),
    }
    session = FakeSession(data)
    regions = ["eu-north-1", "us-east-1"]
    DeclaredStacks(ledger=LedgerName.intended, regions=regions, session=session).fetch()
    observed = Inventory(ledger=LedgerName.observed, regions=regions, session=session).fetch()

    class Finding:
        key = "eni-0vamp"
        records = [_by_key(observed)["eni-0vamp"]]

    creating_events([Finding()], {"session": session})
    assert {"describe_network_interfaces", "describe_addresses"} <= set(session.calls)
    writes = sorted({op for op in session.calls if not op.startswith(READ_PREFIXES)})
    assert writes == []
