# Requirements: Vampires, the night audit of an AWS account

## Introduction

`apps/vampires/` is the first application built on the skeleton. It reconciles one AWS account every night: what the
team approved, what exists, and what appears on the bill. Its user is a startup CTO who reads the report at 08:30,
before anyone has looked at the bill. It uses only read-only AWS calls through the `night-audit` profile (local) or a
read-only IAM role (deployed).

Billing data arrives late, so the control runs at 02:00 UTC on yesterday's bill and uses a grace window of 36 hours.

## Glossary

- **Declared stack**: a CloudFormation stack tagged `night-audit:intended=true`.
- **Approved change**: an entry in `apps/vampires/approved-changes.yaml` naming a resource id, the approver, a reason and
  an expiry date.
- **Exclusion file**: a local, untracked YAML list of resource ids that belong to workloads outside the audited scope.
- **CUR 2.0**: the AWS Cost and Usage Report 2.0 data export delivered as Parquet to S3.

## Requirement 1: the control file

1. THE SYSTEM SHALL ship `apps/vampires/controls/aws-account.yaml` declaring the three ledgers below, the normaliser
   chains `[arn_resource_id, strip, lower]` for every ledger, a 36-hour grace window, and the region names Vampire
   (`OB`), Poltergeist (`O`), Phantom (`B`), Skeleton (`I`), Wraith (`IB`), Familiar (`IO`), Living (`IOB`).
2. WHEN the control file is saved THE SYSTEM SHALL be loadable by the skeleton without code changes in `skeleton/`.

## Requirement 2: intended ledger

1. WHEN the intended ledger is read THE SYSTEM SHALL list every declared stack in every enabled region and emit one
   record per stack resource, keyed by the resource's physical id, with the stack name and logical id as attributes.
2. WHEN `approved-changes.yaml` lists a resource THE SYSTEM SHALL emit one intended record for it with the approver,
   reason and expiry as attributes.
3. WHEN an approved change has passed its expiry date THE SYSTEM SHALL not emit it, and SHALL report the expired entry
   in the run summary.

## Requirement 3: observed ledger

1. WHEN the observed ledger is read THE SYSTEM SHALL list, in every enabled region: EC2 instances, EBS volumes, EBS
   snapshots owned by the account, Elastic IPs, NAT gateways, RDS instances, Lambda functions; and globally: S3 buckets,
   IAM users, IAM access keys, and CloudTrail trails.
2. THE SYSTEM SHALL key each observed record by the resource id that the bill uses for the same resource (instance id,
   volume id, snapshot id, allocation id, NAT gateway id, DB instance identifier, function name, bucket name, user name,
   access key id, trail name), and record its creation time as the timestamp.
3. WHEN a region call fails THE SYSTEM SHALL mark the run incomplete and name the region and service.

## Requirement 4: billed ledger

1. WHEN the billed ledger is read THE SYSTEM SHALL read the CUR 2.0 Parquet files for the current billing period from the
   configured S3 location and emit one record per line item of type `Usage`, keyed by `line_item_resource_id`, with the
   unblended cost as the amount and the product code, usage type and region as attributes.
2. WHEN a usage line has a cost of zero (free tier or credits) THE SYSTEM SHALL still emit it, because the resource is on
   the bill.
3. WHEN a line has no resource id (tax, credits, support) THE SYSTEM SHALL emit it as an unkeyed record.

## Requirement 5: scope

1. WHERE an exclusion file is configured THE SYSTEM SHALL drop records whose normalised key it lists from all three
   ledgers before matching, and report the number excluded.
2. THE SYSTEM SHALL keep the exclusion file out of version control and out of evidence packs, reporting only counts.

## Requirement 6: who created it

1. WHEN a run produces a Vampire or a Poltergeist THE SYSTEM SHALL look up the creating CloudTrail event for that
   resource (for example `RunInstances`, `CreateAccessKey`, `CreateUser`) within the last 90 days and add the event
   time, event name, principal ARN, source IP and user agent to the finding's evidence.
2. IF no creating event is found THEN THE SYSTEM SHALL record "creating event not in CloudTrail event history" as
   evidence.

## Requirement 7: the lab account

1. THE SYSTEM SHALL ship `lab/night-audit-lab.yaml`, a CloudFormation template tagged `night-audit:intended=true` that
   creates a small declared workload: one `t4g.micro` instance, one S3 bucket, one CloudTrail trail and one IAM user.
2. THE SYSTEM SHALL ship `lab/plant.md`, the written procedure that plants one finding of each kind (an untagged
   instance in an unused region, an undeclared access key, a deleted declared trail), and `lab/clean.md` that removes
   them.
3. THE SYSTEM SHALL ship `lab/expected.yaml`, the findings the planted lab must produce, written before the first run.

## Requirement 8: nightly deployment

1. THE SYSTEM SHALL ship an AWS SAM template that deploys the audit as a Lambda function with a read-only role, an
   EventBridge Scheduler rule at 02:00 UTC, an S3 bucket for runs and evidence packs, and a function URL that serves the
   UI and API without login.
2. WHEN the function URL is opened with `?demo=1` THE SYSTEM SHALL serve a recorded run from the repository so the
   product works with no AWS access.
3. THE SYSTEM SHALL tag every deployed resource `night-audit:intended=true` so the audit declares itself.

## Requirement 9: the morning report

1. WHEN a run completes THE SYSTEM SHALL produce a one-page report: counts per region, tonight's new findings first, the
   billed amount of each Vampire and Phantom, and nights persisted.
2. THE SYSTEM SHALL show the same report in the UI and as a downloadable HTML page.

## Requirement 10: What the first real bill taught

The first real CUR 2.0 of the lab account, read by the read-only investigator, showed four conditions that Requirements
2, 3 and 4 did not cover. Each produced false findings on a healthy account.

1. WHEN the observed ledger is read THE SYSTEM SHALL list the network interfaces of every enabled region, including
   requester-managed interfaces (for example those owned by Lambda or a NAT gateway), as records of kind
   `network-interface` keyed by the interface id (`eni-...`), with the attached instance id (`attached_to`), the region,
   the description and the interface type as attributes. An interface has no creation time, so THE SYSTEM SHALL record
   the attachment time as its timestamp when it is attached, so that a new interface is pending during the grace
   window instead of a finding.
2. WHEN a billed usage line names a network interface (for example usage type `<region>-PublicIPv4:InUseAddress`,
   product `AmazonVPC`) THE SYSTEM SHALL key the line by the interface id, so that the charge lands on the interface
   record, which names the instance it belongs to.
3. WHEN a declared stack contains an EC2 instance THE SYSTEM SHALL declare, with that instance, each network interface
   attached to it, recording the instance id as `declared_with`, in the same way as its root volumes (Requirement 2),
   because an interface is not a stack resource.
4. WHEN a billed usage line names a CloudFormation stack (a resource id of the form
   `arn:aws:cloudformation:...:stack/<name>/<uuid>::<LogicalId>`, as on `*Resource-Operation-Count` lines of product
   `AWSCloudFormation`) THE SYSTEM SHALL emit the line as an unkeyed billed record. The line is an operation on a stack,
   not a resource. Its cost SHALL stay in the billed total and in the unkeyed amount, and the line SHALL NOT be hidden.
5. WHEN the physical id of a declared `AWS::EC2::EIP` is a public IP address THE SYSTEM SHALL resolve it to the
   allocation id through `describe_addresses` and key the intended record by the allocation id, because the observed
   ledger and the bill key an Elastic IP by its allocation id.
6. IF no address with that public IP is found THEN THE SYSTEM SHALL keep the physical id as the key, so that the
   declared Elastic IP shows as a Skeleton instead of being dropped silently.
7. THE SYSTEM SHALL make only read calls for these conditions (`describe_network_interfaces`, `describe_instances`,
   `describe_addresses`).
8. WHEN a declared instance has an auto-assigned public IP THE SYSTEM SHALL place the instance, its root volume and its
   network interface in Living and produce no finding for them.
