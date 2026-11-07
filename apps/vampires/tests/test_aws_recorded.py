"""The Vampires connectors against recorded responses: pagination, a region that fails, and a CUR file with odd rows.

``Recorded`` replays responses per region, service and operation. A paginated operation replays its pages in order;
a region listed in ``failing`` raises the error the SDK raises when a region refuses a call. Nothing touches a network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from botocore.exceptions import ClientError
from nightaudit.models import LedgerName
from nightaudit.runner import run_control
from vampires import aws
from vampires.aws import CostAndUsage, DeclaredStacks, Inventory

T0 = datetime(2026, 10, 1, tzinfo=UTC)
RUN = datetime(2026, 11, 6, 2, 0, tzinfo=UTC)


class _Pages:
    def __init__(self, pages: list[dict[str, Any]], asked: list[dict[str, Any]]) -> None:
        self._pages, self._asked = pages, asked

    def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
        self._asked.append(kwargs)
        return self._pages


class _Client:
    def __init__(self, session: Recorded, service: str, region: str) -> None:
        self._session, self._service, self._region = session, service, region

    def _answer(self, op: str) -> Any:
        self._session.calls.append(f"{self._region}/{self._service}/{op}")
        if self._region in self._session.failing:
            raise ClientError({"Error": {"Code": "UnauthorizedOperation", "Message": "region refused"}}, op)
        return self._session.data.get(self._region, {}).get(self._service, {}).get(op, {})

    def get_paginator(self, op: str) -> _Pages:
        answer = self._answer(op)
        return _Pages(answer if isinstance(answer, list) else [answer], self._session.asked)

    def __getattr__(self, op: str) -> Any:
        return lambda **_: self._answer(op)


class Recorded:
    """A boto3 session that replays recorded responses."""

    def __init__(self, data: dict[str, Any], failing: tuple[str, ...] = ()) -> None:
        self.data, self.failing = data, failing
        self.calls: list[str] = []
        self.asked: list[dict[str, Any]] = []

    def client(self, service: str, region_name: str) -> _Client:
        return _Client(self, service, region_name)


def _instance(instance_id: str) -> dict[str, Any]:
    return {"InstanceId": instance_id, "LaunchTime": T0, "InstanceType": "t4g.micro", "State": {"Name": "running"}}


#: Three pages of instances in one region, and two pages of IAM users each with one page of keys.
PAGED = {
    "eu-north-1": {
        "ec2": {
            "describe_instances": [
                {"Reservations": [{"Instances": [_instance("i-0001"), _instance("i-0002")]}], "NextToken": "p2"},
                {"Reservations": [{"Instances": [_instance("i-0003")]}], "NextToken": "p3"},
                {"Reservations": [{"Instances": [_instance("i-0004")]}]},
            ],
        },
    },
    "us-east-1": {
        "iam": {
            "list_users": [
                {"Users": [{"UserName": "a", "CreateDate": T0}], "Marker": "m2", "IsTruncated": True},
                {"Users": [{"UserName": "b", "CreateDate": T0}], "IsTruncated": False},
            ],
        },
    },
}


def test_inventory_reads_every_page_of_a_paginated_listing() -> None:
    records = Inventory(ledger=LedgerName.observed, regions=["eu-north-1"], session=Recorded(PAGED)).fetch()
    instances = [r.raw_key for r in records if r.attrs["kind"] == "ec2-instance"]
    users = [r.raw_key for r in records if r.attrs["kind"] == "iam-user"]
    assert (instances, users) == (["i-0001", "i-0002", "i-0003", "i-0004"], ["a", "b"])


def test_inventory_asks_for_live_instances_and_only_its_own_snapshots() -> None:
    session = Recorded(PAGED)
    Inventory(ledger=LedgerName.observed, regions=["eu-north-1"], session=session).fetch()
    states = next(a["Filters"][0]["Values"] for a in session.asked if "Filters" in a)
    assert states == ["pending", "running", "stopping", "stopped"]  # terminated instances are not in the ledger
    assert {"OwnerIds": ["self"]} in session.asked


def test_an_empty_region_adds_nothing_and_a_healthy_empty_account_has_no_records() -> None:
    assert Inventory(ledger=LedgerName.observed, regions=["ap-south-1"], session=Recorded({})).fetch() == []


def test_a_region_that_refuses_a_call_fails_the_inventory_and_names_the_region() -> None:
    session = Recorded(PAGED, failing=("eu-north-1",))
    with pytest.raises(RuntimeError, match=r"inventory failed in eu-north-1: ClientError"):
        Inventory(ledger=LedgerName.observed, regions=["us-west-2", "eu-north-1"], session=session).fetch()
    assert session.calls[0].startswith("us-west-2/")  # the region before it was read first


def test_global_services_that_refuse_a_call_fail_the_inventory_and_say_so() -> None:
    with pytest.raises(RuntimeError, match="inventory failed for global services"):
        Inventory(ledger=LedgerName.observed, regions=[], session=Recorded({}, failing=("us-east-1",))).fetch()


def test_enabled_regions_are_read_from_the_account_in_a_fixed_order() -> None:
    regions = {"Regions": [{"RegionName": "eu-north-1"}, {"RegionName": "ap-south-1"}, {"RegionName": "us-east-1"}]}
    session = Recorded({"us-east-1": {"ec2": {"describe_regions": regions}}})
    assert Inventory(ledger=LedgerName.observed, session=session).regions() == ["ap-south-1", "eu-north-1", "us-east-1"]


def test_declared_stacks_read_every_page_of_stacks_and_of_their_resources() -> None:
    def resource(logical: str, physical: str) -> dict[str, str]:
        return {
            "LogicalResourceId": logical,
            "PhysicalResourceId": physical,
            "ResourceType": "AWS::S3::Bucket",
            "ResourceStatus": "CREATE_COMPLETE",
        }

    tagged = [{"Key": "night-audit:intended", "Value": "TRUE"}]
    data = {
        "us-east-1": {
            "cloudformation": {
                "describe_stacks": [
                    {"Stacks": [{"StackName": "one", "Tags": tagged}], "NextToken": "2"},
                    {"Stacks": [{"StackName": "two", "Tags": [{"Key": "night-audit:intended", "Value": "no"}]}]},
                ],
                "list_stack_resources": [
                    {"StackResourceSummaries": [resource("A", "bucket-a")], "NextToken": "2"},
                    {
                        "StackResourceSummaries": [
                            resource("B", "bucket-b"),
                            {**resource("C", "gone"), "ResourceStatus": "DELETE_COMPLETE"},
                        ]
                    },
                ],
            }
        }
    }
    records = DeclaredStacks(ledger=LedgerName.intended, regions=["us-east-1"], session=Recorded(data)).fetch()
    assert [r.raw_key for r in records] == ["bucket-a", "bucket-b"]


CONTROL = """\
id: recorded-account
grace_hours: 24
ledgers:
  intended:
    key_field: id
    normalisers: [strip, lower]
    connector: {type: csv, path: intended.csv}
  observed:
    key_field: id
    normalisers: [strip, lower]
    connector: {type: python, entry: 'vampires.aws:Inventory', options: {regions: [us-west-2, eu-north-1]}}
  billed:
    key_field: resource
    normalisers: [arn_resource_id, strip, lower]
    connector: {type: csv, path: billed.csv}
"""


@pytest.mark.integration
def test_a_failing_region_makes_the_observed_ledger_missing_and_the_night_has_no_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(aws, "_session", lambda profile: Recorded(PAGED, failing=("eu-north-1",)))
    (tmp_path / "control.yaml").write_text(CONTROL, encoding="utf-8")
    (tmp_path / "intended.csv").write_text("row_id,id\ni1,i-0001\n", encoding="utf-8")
    (tmp_path / "billed.csv").write_text("row_id,resource,amount\nb1,i-0009,5.00\n", encoding="utf-8")
    result = run_control(tmp_path / "control.yaml", tmp_path / "runs", run_time=RUN)
    assert (result.complete, result.missing_ledgers, result.findings) == (False, ["observed"], [])
    assert "inventory failed in eu-north-1" in result.ledger_errors["observed"]


@pytest.mark.integration
def test_the_same_account_with_every_region_answering_gives_its_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(aws, "_session", lambda profile: Recorded(PAGED))
    (tmp_path / "control.yaml").write_text(CONTROL, encoding="utf-8")
    (tmp_path / "intended.csv").write_text("row_id,id\ni1,i-0001\n", encoding="utf-8")
    (tmp_path / "billed.csv").write_text("row_id,resource,amount\nb1,i-0001,1.00\nb2,i-0009,5.00\n", encoding="utf-8")
    result = run_control(tmp_path / "control.yaml", tmp_path / "runs", run_time=RUN)
    assert result.complete
    assert {k: v for k, v in result.regions.items() if v != "O"} == {"i-0001": "IOB", "i-0009": "B"}


Row = dict[str, Any]


def _line(**overrides: Any) -> Row:
    row: Row = {
        "line_item_usage_start_date": datetime(2026, 11, 5, tzinfo=UTC),
        "line_item_line_item_type": "Usage",
        "line_item_product_code": "AmazonEC2",
        "line_item_usage_type": "BoxUsage:t4g.micro",
        "line_item_resource_id": "i-0001",
        "line_item_usage_amount": 1.0,
        "line_item_unblended_cost": 0.0084,
        "product_region_code": "eu-north-1",
    }
    row.update(overrides)
    return row


def _cur(tmp_path: Path, rows: list[Row]) -> CostAndUsage:
    folder = tmp_path / "cur"
    folder.mkdir(exist_ok=True)
    schema = pa.schema(
        [
            ("line_item_usage_start_date", pa.timestamp("us", tz="UTC")),
            ("line_item_line_item_type", pa.string()),
            ("line_item_product_code", pa.string()),
            ("line_item_usage_type", pa.string()),
            ("line_item_resource_id", pa.string()),
            ("line_item_usage_amount", pa.float64()),
            ("line_item_unblended_cost", pa.float64()),
            ("product_region_code", pa.string()),
        ]
    )
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), folder / f"part-{len(list(folder.iterdir()))}.parquet")
    return CostAndUsage(ledger=LedgerName.billed, path=str(folder), billing_period="2026-11")


@pytest.mark.parametrize(
    ("overrides", "key", "amount"),
    [
        ({"line_item_unblended_cost": None, "line_item_usage_amount": None}, "i-0001", Decimal(0)),
        ({"line_item_usage_start_date": None}, "i-0001", Decimal("0.0084")),
        ({"line_item_resource_id": None}, "", Decimal("0.0084")),
        ({"line_item_resource_id": ""}, "", Decimal("0.0084")),
        ({"line_item_line_item_type": "Tax", "line_item_unblended_cost": 1.5}, "", Decimal("1.5")),
        ({"line_item_line_item_type": "Credit", "line_item_unblended_cost": -0.0084}, "", Decimal("-0.0084")),
        ({"line_item_line_item_type": "SavingsPlanCoveredUsage"}, "i-0001", Decimal("0.0084")),
        ({"line_item_line_item_type": None}, "", Decimal("0.0084")),
        (
            {"line_item_resource_id": "arn:aws:cloudformation:eu-north-1:111122223333:stack/lab/uuid::Web"},
            "",
            Decimal("0.0084"),
        ),
    ],
    ids=[
        "null-cost",
        "null-date",
        "null-resource",
        "empty-resource",
        "tax-with-resource",
        "credit",
        "savings-plan",
        "null-line-type",
        "stack-arn",
    ],
)
def test_an_odd_cur_line_is_kept_with_its_exact_amount_and_keyed_only_when_it_is_usage_of_a_resource(
    tmp_path: Path, overrides: Row, key: str, amount: Decimal
) -> None:
    (record,) = _cur(tmp_path, [_line(**overrides)]).fetch()
    assert (record.raw_key, record.amount, record.attrs["line_items"]) == (key, amount, "1")


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), float("-inf")])
def test_a_cur_cost_that_is_not_finite_stops_the_ledger(tmp_path: Path, cost: float) -> None:
    with pytest.raises(ValueError, match="not a finite number"):
        _cur(tmp_path, [_line(), _line(line_item_unblended_cost=cost)]).fetch()


def test_a_cur_folder_with_two_files_sums_lines_across_them(tmp_path: Path) -> None:
    _cur(tmp_path, [_line()])
    (record,) = _cur(tmp_path, [_line(line_item_usage_start_date=datetime(2026, 11, 4, tzinfo=UTC))]).fetch()
    assert (record.amount, record.attrs["line_items"]) == (Decimal("0.0168"), "2")
    assert record.timestamp == datetime(2026, 11, 4, tzinfo=UTC)  # the earliest line's start


def test_a_cur_folder_with_no_parquet_file_stops_the_ledger(tmp_path: Path) -> None:
    (tmp_path / "cur").mkdir()
    (tmp_path / "cur" / "notes.txt").write_text("not a report", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="no parquet files"):
        CostAndUsage(ledger=LedgerName.billed, path=str(tmp_path / "cur")).fetch()


def test_a_cur_file_without_a_required_column_stops_the_ledger(tmp_path: Path) -> None:
    (tmp_path / "cur").mkdir()
    pq.write_table(pa.table({"line_item_resource_id": ["i-0001"]}), tmp_path / "cur" / "part-0.parquet")
    with pytest.raises(Exception, match="line_item_usage_start_date"):
        CostAndUsage(ledger=LedgerName.billed, path=str(tmp_path / "cur")).fetch()


def test_a_cur_file_that_is_not_parquet_stops_the_ledger(tmp_path: Path) -> None:
    (tmp_path / "cur").mkdir()
    (tmp_path / "cur" / "part-0.parquet").write_bytes(b"PAR1 but not really")
    with pytest.raises(pa.ArrowInvalid):
        CostAndUsage(ledger=LedgerName.billed, path=str(tmp_path / "cur")).fetch()


def test_an_empty_cur_file_is_an_empty_bill(tmp_path: Path) -> None:
    assert _cur(tmp_path, []).fetch() == []


def test_the_cur_bucket_is_listed_page_by_page_and_only_parquet_objects_are_read(tmp_path: Path) -> None:
    body = tmp_path / "body.parquet"
    pq.write_table(pa.Table.from_pylist([_line()]), body)

    class _Body:
        def read(self) -> bytes:
            return body.read_bytes()

    listing = [
        {"Contents": [{"Key": "cur2/x/data/BILLING_PERIOD=2026-11/a.parquet"}], "NextContinuationToken": "2"},
        {"Contents": [{"Key": "cur2/x/data/BILLING_PERIOD=2026-11/manifest.json"}]},
        {"Contents": [{"Key": "cur2/x/data/BILLING_PERIOD=2026-11/b.parquet"}]},
    ]
    session = Recorded({"us-east-1": {"s3": {"list_objects_v2": listing, "get_object": {"Body": _Body()}}}})
    connector = CostAndUsage(
        ledger=LedgerName.billed, bucket="cur-bucket", export="x", billing_period="2026-11", session=session
    )
    (record,) = connector.fetch()
    assert (record.amount, record.attrs["line_items"]) == (Decimal("0.0168"), "2")
    assert [c for c in session.calls if c.endswith("get_object")] == ["us-east-1/s3/get_object"] * 2
    assert session.asked == [{"Bucket": "cur-bucket", "Prefix": "cur2/x/data/BILLING_PERIOD=2026-11/"}]


def test_a_cur_bucket_with_nothing_for_the_period_stops_the_ledger() -> None:
    session = Recorded({"us-east-1": {"s3": {"list_objects_v2": [{"Contents": []}]}}})
    connector = CostAndUsage(ledger=LedgerName.billed, bucket="cur-bucket", billing_period="2026-11", session=session)
    with pytest.raises(FileNotFoundError, match="no CUR 2.0 data yet"):
        connector.fetch()
