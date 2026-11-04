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
from nightaudit.models import LedgerName, LedgerSnapshot
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
    def __init__(self, service: str, region: str, data: dict[str, Any]) -> None:
        self._service, self._region, self._data = service, region, data

    def _get(self, op: str) -> Any:
        return self._data.get(self._region, {}).get(self._service, {}).get(op, {})

    def get_paginator(self, op: str) -> FakePaginator:
        return FakePaginator([self._get(op)])

    def __getattr__(self, op: str) -> Any:
        return lambda **_: self._get(op)


class FakeSession:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def client(self, service: str, region_name: str) -> FakeClient:
        return FakeClient(service, region_name, self.data)


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


def _cur(tmp: Path) -> Path:
    rows = [
        ("Usage", "AmazonEC2", "BoxUsage:t4g.micro", "i-0lab", "0", "us-east-1"),
        ("Usage", "AmazonEC2", "BoxUsage:t4g.micro", "i-0lab", "0", "us-east-1"),
        ("Usage", "AmazonEC2", "EUN1-BoxUsage:t4g.micro", "i-0vamp", "0.2016", "eu-north-1"),
        ("Usage", "AmazonEC2", "EUN1-EBS:VolumeUsage.gp3", "arn:aws:ec2:eu-north-1:111122223333:volume/vol-0vamp",
         "0.02", "eu-north-1"),
        ("Usage", "AmazonEC2", "EBS:VolumeUsage.gp3", "vol-0lab", "0", "us-east-1"),
        ("Credit", "AmazonEC2", "", "", "-0.2216", ""),
    ]
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
