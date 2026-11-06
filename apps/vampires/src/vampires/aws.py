"""Read-only AWS connectors for the Vampires app.

Every call here is a Describe, List, Get or LookupEvents call. The deployed function runs under a role with
``ReadOnlyAccess``; locally the ``night-audit`` profile has the same rights.
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha1
from pathlib import Path
from typing import Any

import yaml
from nightaudit.connectors import Connector
from nightaudit.models import LedgerName, Record

INTENDED_TAG = "night-audit:intended"

#: CloudFormation resource types whose physical id is the id the inventory and the bill use.
AUDITED_STACK_TYPES: dict[str, str] = {
    "AWS::EC2::Instance": "ec2-instance",
    "AWS::EC2::Volume": "ebs-volume",
    "AWS::EC2::EIP": "elastic-ip",
    "AWS::EC2::NatGateway": "nat-gateway",
    "AWS::RDS::DBInstance": "rds-instance",
    "AWS::Lambda::Function": "lambda-function",
    "AWS::S3::Bucket": "s3-bucket",
    "AWS::IAM::User": "iam-user",
    "AWS::IAM::AccessKey": "iam-access-key",
    "AWS::CloudTrail::Trail": "cloudtrail-trail",
}

GLOBAL_REGION = "us-east-1"


def _session(profile: str | None) -> Any:
    import boto3

    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return boto3.Session()  # deployed: the function's read-only role, never a named profile
    profile = profile or os.environ.get("NIGHT_AUDIT_PROFILE") or None
    return boto3.Session(profile_name=profile) if profile else boto3.Session()


def _iso(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return None


def _name_tag(tags: Iterable[dict[str, str]] | None) -> str:
    for tag in tags or []:
        if tag.get("Key") == "Name":
            return tag.get("Value", "")
    return ""


def _paginate(client: Any, operation: str, result_key: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
    paginator = client.get_paginator(operation)
    for page in paginator.paginate(**kwargs):
        yield from page.get(result_key, [])


class _AwsConnector(Connector):
    """Shared plumbing: session, regions, read-only declaration."""

    def __init__(
        self,
        ledger: LedgerName,
        key_field: str = "",
        base_dir: Path | None = None,
        profile: str | None = None,
        regions: list[str] | str = "enabled",
        session: Any = None,
        **_: Any,
    ) -> None:
        self._ledger = ledger
        self._base_dir = base_dir
        self._profile = profile
        self._regions_option = regions
        self._session_obj = session

    @property
    def ledger(self) -> LedgerName:
        return self._ledger

    @property
    def read_only(self) -> bool:
        return True

    @property
    def session(self) -> Any:
        if self._session_obj is None:
            self._session_obj = _session(self._profile)
        return self._session_obj

    def regions(self) -> list[str]:
        if isinstance(self._regions_option, list):
            return list(self._regions_option)
        ec2 = self.session.client("ec2", region_name=GLOBAL_REGION)
        response = ec2.describe_regions(
            Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
        )
        return sorted(r["RegionName"] for r in response["Regions"])

    def _record(self, row_id: str, key: str, ts: datetime | None, **attrs: Any) -> Record:
        return Record(
            ledger=self._ledger,
            source=self.source,
            row_id=row_id,
            raw_key=key,
            timestamp=ts,
            attrs={k: str(v) for k, v in attrs.items() if v not in (None, "")},
        )


class DeclaredStacks(_AwsConnector):
    """Intended ledger: resources of CloudFormation stacks tagged ``night-audit:intended=true``.

    Root volumes of a declared instance are declared with it (they are not stack resources).
    """

    @property
    def source(self) -> str:
        return "cloudformation:declared-stacks"

    def fetch(self) -> list[Record]:
        records: list[Record] = []
        for region in self.regions():
            cfn = self.session.client("cloudformation", region_name=region)
            instances: list[str] = []
            for stack in _paginate(cfn, "describe_stacks", "Stacks"):
                tags = {t["Key"]: t["Value"] for t in stack.get("Tags", [])}
                if tags.get(INTENDED_TAG, "").lower() != "true":
                    continue
                stack_name = stack["StackName"]
                for res in _paginate(cfn, "list_stack_resources", "StackResourceSummaries", StackName=stack_name):
                    kind = AUDITED_STACK_TYPES.get(res["ResourceType"])
                    physical = res.get("PhysicalResourceId")
                    if kind is None or not physical or res.get("ResourceStatus", "").startswith("DELETE"):
                        continue
                    records.append(
                        self._record(
                            f"{region}/{stack_name}/{res['LogicalResourceId']}",
                            physical,
                            None,
                            kind=kind,
                            stack=stack_name,
                            logical_id=res["LogicalResourceId"],
                            region=region,
                        )
                    )
                    if kind == "ec2-instance":
                        instances.append(physical)
            if instances:
                records.extend(self._root_volumes(region, instances))
        return records

    def _root_volumes(self, region: str, instance_ids: list[str]) -> list[Record]:
        ec2 = self.session.client("ec2", region_name=region)
        out: list[Record] = []
        for reservation in _paginate(ec2, "describe_instances", "Reservations", InstanceIds=instance_ids):
            for inst in reservation.get("Instances", []):
                for mapping in inst.get("BlockDeviceMappings", []):
                    volume = mapping.get("Ebs", {}).get("VolumeId")
                    if volume:
                        out.append(
                            self._record(
                                f"{region}/{inst['InstanceId']}/{volume}",
                                volume,
                                None,
                                kind="ebs-volume",
                                declared_with=inst["InstanceId"],
                                region=region,
                            )
                        )
        return out


class ApprovedChanges(_AwsConnector):
    """Intended ledger: resources approved outside a stack, with approver, reason and expiry."""

    def __init__(
        self, path: str = "approved-changes.yaml", today: str | None = None, optional: bool = False, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self._path = path
        self._optional = optional
        self._today = date.fromisoformat(today) if today else datetime.now(UTC).date()
        self.expired: list[str] = []

    @property
    def source(self) -> str:
        return f"file:{self._path}"

    def fetch(self) -> list[Record]:
        path = Path(self._path)
        if not path.is_absolute() and self._base_dir is not None:
            path = self._base_dir / path
        if self._optional and not path.exists():
            return []
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        records: list[Record] = []
        for index, entry in enumerate(raw.get("approved", []), start=1):
            expires = entry.get("expires")
            if expires and date.fromisoformat(str(expires)) < self._today:
                self.expired.append(str(entry.get("id")))
                continue
            records.append(
                self._record(
                    f"approved/{index}",
                    str(entry["id"]),
                    None,
                    approver=entry.get("approver"),
                    reason=entry.get("reason"),
                    expires=expires,
                )
            )
        return records


class Inventory(_AwsConnector):
    """Observed ledger: what exists, in every enabled region, plus global services."""

    @property
    def source(self) -> str:
        return "aws:inventory"

    def fetch(self) -> list[Record]:
        records: list[Record] = []
        for region in self.regions():
            records.extend(self._regional(region))
        records.extend(self._global())
        return records

    def _regional(self, region: str) -> list[Record]:
        out: list[Record] = []
        try:
            ec2 = self.session.client("ec2", region_name=region)
            filters = [{"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}]
            for reservation in _paginate(ec2, "describe_instances", "Reservations", Filters=filters):
                for inst in reservation.get("Instances", []):
                    out.append(
                        self._record(
                            f"{region}/ec2/{inst['InstanceId']}",
                            inst["InstanceId"],
                            _iso(inst.get("LaunchTime")),
                            kind="ec2-instance",
                            region=region,
                            instance_type=inst.get("InstanceType"),
                            state=inst.get("State", {}).get("Name"),
                            Name=_name_tag(inst.get("Tags")),
                        )
                    )
            for vol in _paginate(ec2, "describe_volumes", "Volumes"):
                attached = ",".join(a["InstanceId"] for a in vol.get("Attachments", []) if "InstanceId" in a)
                out.append(
                    self._record(
                        f"{region}/ebs/{vol['VolumeId']}",
                        vol["VolumeId"],
                        _iso(vol.get("CreateTime")),
                        kind="ebs-volume",
                        region=region,
                        size_gib=vol.get("Size"),
                        attached_to=attached,
                    )
                )
            for snap in _paginate(ec2, "describe_snapshots", "Snapshots", OwnerIds=["self"]):
                out.append(
                    self._record(
                        f"{region}/snapshot/{snap['SnapshotId']}",
                        snap["SnapshotId"],
                        _iso(snap.get("StartTime")),
                        kind="ebs-snapshot",
                        region=region,
                    )
                )
            for addr in ec2.describe_addresses().get("Addresses", []):
                if addr.get("AllocationId"):
                    out.append(
                        self._record(
                            f"{region}/eip/{addr['AllocationId']}",
                            addr["AllocationId"],
                            None,
                            kind="elastic-ip",
                            region=region,
                            associated_with=addr.get("InstanceId"),
                        )
                    )
            for nat in _paginate(ec2, "describe_nat_gateways", "NatGateways"):
                if nat.get("State") in ("pending", "available"):
                    out.append(
                        self._record(
                            f"{region}/nat/{nat['NatGatewayId']}",
                            nat["NatGatewayId"],
                            _iso(nat.get("CreateTime")),
                            kind="nat-gateway",
                            region=region,
                        )
                    )
            rds = self.session.client("rds", region_name=region)
            for db in _paginate(rds, "describe_db_instances", "DBInstances"):
                out.append(
                    self._record(
                        f"{region}/rds/{db['DBInstanceIdentifier']}",
                        db["DBInstanceIdentifier"],
                        _iso(db.get("InstanceCreateTime")),
                        kind="rds-instance",
                        region=region,
                        db_class=db.get("DBInstanceClass"),
                    )
                )
            lam = self.session.client("lambda", region_name=region)
            for fn in _paginate(lam, "list_functions", "Functions"):
                out.append(
                    self._record(
                        f"{region}/lambda/{fn['FunctionName']}",
                        fn["FunctionName"],
                        None,
                        kind="lambda-function",
                        region=region,
                        runtime=fn.get("Runtime"),
                    )
                )
        except Exception as exc:
            raise RuntimeError(f"inventory failed in {region}: {type(exc).__name__}: {exc}") from exc
        return out

    def _global(self) -> list[Record]:
        out: list[Record] = []
        try:
            s3 = self.session.client("s3", region_name=GLOBAL_REGION)
            for bucket in s3.list_buckets().get("Buckets", []):
                out.append(
                    self._record(
                        f"global/s3/{bucket['Name']}",
                        bucket["Name"],
                        _iso(bucket.get("CreationDate")),
                        kind="s3-bucket",
                        region="global",
                    )
                )
            iam = self.session.client("iam", region_name=GLOBAL_REGION)
            for user in _paginate(iam, "list_users", "Users"):
                out.append(
                    self._record(
                        f"global/iam-user/{user['UserName']}",
                        user["UserName"],
                        _iso(user.get("CreateDate")),
                        kind="iam-user",
                        region="global",
                    )
                )
                for key in _paginate(iam, "list_access_keys", "AccessKeyMetadata", UserName=user["UserName"]):
                    out.append(
                        self._record(
                            f"global/iam-key/{key['AccessKeyId']}",
                            key["AccessKeyId"],
                            _iso(key.get("CreateDate")),
                            kind="iam-access-key",
                            region="global",
                            user=user["UserName"],
                            status=key.get("Status"),
                        )
                    )
            trail = self.session.client("cloudtrail", region_name=GLOBAL_REGION)
            for t in trail.describe_trails(includeShadowTrails=False).get("trailList", []):
                out.append(
                    self._record(
                        f"global/trail/{t['Name']}",
                        t["Name"],
                        None,
                        kind="cloudtrail-trail",
                        region=t.get("HomeRegion", "global"),
                    )
                )
        except Exception as exc:
            raise RuntimeError(f"inventory failed for global services: {type(exc).__name__}: {exc}") from exc
        return out


USAGE_LINE_TYPES = {"Usage", "DiscountedUsage", "SavingsPlanCoveredUsage"}
CUR_COLUMNS = [
    "line_item_usage_start_date",
    "line_item_line_item_type",
    "line_item_product_code",
    "line_item_usage_type",
    "line_item_resource_id",
    "line_item_usage_amount",
    "line_item_unblended_cost",
    "product_region_code",
]


class CostAndUsage(_AwsConnector):
    """Billed ledger: CUR 2.0 Parquet for one billing period, one record per resource and usage type.

    Usage lines are summed per (resource id, product, usage type). A line on the bill counts even when its cost is
    zero (free tier, credits). Lines with no resource id (tax, credits, support) become unkeyed records.
    """

    def __init__(
        self,
        bucket: str | None = None,
        prefix: str = "cur2",
        export: str = "night-audit-cur2",
        billing_period: str | None = None,
        path: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._export = export
        self._period = billing_period or datetime.now(UTC).strftime("%Y-%m")
        self._path = path

    @property
    def source(self) -> str:
        if self._path:
            return f"cur2:{self._path}"
        return f"cur2:s3://{self._bucket}/{self._prefix}/{self._export}/BILLING_PERIOD={self._period}"

    def _tables(self) -> list[Any]:
        import pyarrow.parquet as pq

        if self._path:
            folder = Path(self._path)
            if not folder.is_absolute() and self._base_dir is not None:
                folder = self._base_dir / folder
            files = sorted(folder.glob("*.parquet"))
            if not files:
                raise FileNotFoundError(f"no parquet files in {folder}")
            return [pq.read_table(f, columns=CUR_COLUMNS) for f in files]
        if not self._bucket:
            raise ValueError("CostAndUsage needs a bucket or a local path")
        s3 = self.session.client("s3", region_name=GLOBAL_REGION)
        prefix = f"{self._prefix}/{self._export}/data/BILLING_PERIOD={self._period}/"
        keys = [
            obj["Key"]
            for obj in _paginate(s3, "list_objects_v2", "Contents", Bucket=self._bucket, Prefix=prefix)
            if obj["Key"].endswith(".parquet")
        ]
        if not keys:
            raise FileNotFoundError(f"no CUR 2.0 data yet under s3://{self._bucket}/{prefix}")
        tables = []
        for key in keys:
            body = s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
            tables.append(pq.read_table(io.BytesIO(body), columns=CUR_COLUMNS))
        return tables

    def fetch(self) -> list[Record]:
        groups: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        for table in self._tables():
            for row in table.to_pylist():
                line_type = str(row.get("line_item_line_item_type") or "")
                resource = str(row.get("line_item_resource_id") or "") if line_type in USAGE_LINE_TYPES else ""
                group_key = (
                    resource,
                    line_type if not resource else "usage",
                    str(row.get("line_item_product_code") or ""),
                    str(row.get("line_item_usage_type") or ""),
                    str(row.get("product_region_code") or ""),
                )
                group = groups.setdefault(
                    group_key, {"cost": Decimal("0"), "usage": Decimal("0"), "lines": 0, "start": None}
                )
                group["cost"] += Decimal(str(row.get("line_item_unblended_cost") or 0))
                group["usage"] += Decimal(str(row.get("line_item_usage_amount") or 0))
                group["lines"] += 1
                start = _iso(row.get("line_item_usage_start_date"))
                if start and (group["start"] is None or start < group["start"]):
                    group["start"] = start
        records: list[Record] = []
        for (resource, line_type, product, usage_type, region), g in sorted(groups.items()):
            row_id = sha1("|".join((resource, line_type, product, usage_type, region)).encode()).hexdigest()[:12]
            records.append(
                Record(
                    ledger=self._ledger,
                    source=self.source,
                    row_id=f"cur/{row_id}",
                    raw_key=resource,
                    amount=g["cost"].quantize(Decimal("0.0000001")).normalize(),
                    timestamp=g["start"],
                    attrs={
                        k: v
                        for k, v in {
                            "product": product,
                            "usage_type": usage_type,
                            "region": region,
                            "line_type": "Usage" if line_type == "usage" else line_type,
                            "usage_amount": str(g["usage"].normalize()),
                            "line_items": str(g["lines"]),
                            "billing_period": self._period,
                        }.items()
                        if v
                    },
                )
            )
        return records


CREATE_EVENTS = {
    "RunInstances",
    "CreateVolume",
    "CreateSnapshot",
    "AllocateAddress",
    "CreateNatGateway",
    "CreateDBInstance",
    "CreateFunction20150331",
    "CreateFunction",
    "CreateBucket",
    "CreateUser",
    "CreateAccessKey",
    "CreateTrail",
}


def creating_events(findings: list[Any], options: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Enricher: the CloudTrail event that created each finding's resource (Vampires Req 6).

    Uses ``LookupEvents`` (event history, last 90 days) in the resource's region; IAM and S3 events are read in
    us-east-1. Returns a mapping of finding key to context fields.
    """
    session = options.get("session") or _session(options.get("profile"))
    out: dict[str, dict[str, str]] = {}
    for finding in findings:
        region = GLOBAL_REGION
        name = finding.key
        for record in finding.records:
            if record.ledger == LedgerName.observed:
                name = record.raw_key
                rec_region = record.attrs.get("region", "global")
                region = rec_region if rec_region not in ("global", "") else GLOBAL_REGION
                break
        client = session.client("cloudtrail", region_name=region)
        response = client.lookup_events(
            LookupAttributes=[{"AttributeKey": "ResourceName", "AttributeValue": name}], MaxResults=50
        )
        events = [e for e in response.get("Events", []) if e.get("EventName") in CREATE_EVENTS]
        if not events:
            out[finding.key] = {"creating_event": "creating event not in CloudTrail event history"}
            continue
        first = min(events, key=lambda e: e["EventTime"])
        detail = _event_detail(first)
        created = _iso(first["EventTime"])
        out[finding.key] = {
            "creating_event": first["EventName"],
            "created_at": created.isoformat() if created else "",
            "created_by": detail.get("principal", first.get("Username", "")),
            "source_ip": detail.get("source_ip", ""),
            "user_agent": detail.get("user_agent", "")[:120],
        }
    return out


def _event_detail(event: dict[str, Any]) -> dict[str, str]:
    import json

    try:
        raw = json.loads(event.get("CloudTrailEvent", "{}"))
    except (TypeError, ValueError):
        return {}
    identity = raw.get("userIdentity", {})
    return {
        "principal": identity.get("arn") or identity.get("type", ""),
        "source_ip": raw.get("sourceIPAddress", ""),
        "user_agent": raw.get("userAgent", ""),
    }
