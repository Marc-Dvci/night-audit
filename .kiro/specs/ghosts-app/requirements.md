# Requirements: Ghosts, the access review that reconciles people

## Introduction

`apps/ghosts/` is the second application built on the same skeleton. It reconciles staff access: who HR says should have
access, which accounts exist, and which seats the company pays for. Its user is an IT manager preparing a quarterly
access review that an auditor will test. The skeleton is unchanged; the app supplies connectors, a control file and
its own region names.

The company in the demo is Hollow Pines Credit Union, about 180 staff. Its names, addresses and vendors never match a
real person or product.

## Glossary

- **HR roster**: CSV export of employees and contractors with start date, leaving date (if any), department and manager.
- **Identity export**: CSV export of accounts from an identity provider, with status and last sign-in.
- **Licence assignments**: per-vendor CSV of the people a paid seat is assigned to.
- **Seat invoice**: per-vendor monthly invoice with a seat quantity and a unit price.
- **Vendors**: Lantern Chat, Crypt Docs, Belfry CRM, Ossuary Design. No real product names.

## Requirement 1: the control file

1. THE SYSTEM SHALL ship `apps/ghosts/controls/staff-access.yaml` declaring the ledgers below, the normaliser chain
   `[email_canonical]` with the alias domain `hollowpines.org` mapped to `hollowpines.com`, a grace window of 72 hours,
   and the region names Ghost (`OB`), Poltergeist (`O`), Phantom seat (`B`), Unprovisioned joiner (`I`), Wraith
   (`IB`), Unlicensed user (`IO`), Living (`IOB`).

## Requirement 2: intended ledger

1. WHEN the intended ledger is read THE SYSTEM SHALL emit one record per person in the HR roster whose leaving date is
   empty or later than the run date, keyed by work email.
2. WHEN a person has left THE SYSTEM SHALL not emit an intended record, and SHALL keep the leaving date available as
   evidence for any finding on that key.

## Requirement 3: observed ledger

1. WHEN the observed ledger is read THE SYSTEM SHALL emit one record per active account in each identity export,
   keyed by email, with the system name, status and last sign-in as attributes.
2. THE SYSTEM SHALL support at least two observed sources in one run: the demo identity provider export and one
   live source, the members of a GitHub organisation read through the GitHub API with a read-only token.

## Requirement 4: billed ledger

1. WHEN the billed ledger is read THE SYSTEM SHALL emit one record per licence assignment, keyed by email, with the
   vendor and the unit price from that vendor's invoice as the amount.
2. WHEN a vendor's invoice quantity exceeds its number of licence assignments THE SYSTEM SHALL emit the difference as
   unkeyed billed records (seats paid for nobody named), each with the unit price.
3. WHEN a vendor's invoice quantity is lower than its number of licence assignments THE SYSTEM SHALL report the
   difference in the run summary.

## Requirement 5: the review campaign

1. WHEN a run completes THE SYSTEM SHALL export a review sheet (CSV and HTML) with one line per finding: person,
   region name, systems, seats, leaving date, last sign-in, manager, and empty columns for the reviewer's decision
   and date.
2. WHEN a completed review sheet is imported THE SYSTEM SHALL record each decision in the evidence pack with the
   reviewer's name and date, and SHALL refuse a decision on a key that the run did not report.

## Requirement 6: demo company

1. THE SYSTEM SHALL ship a seeded generator for Hollow Pines that writes the HR roster, the identity export, the licence
   assignments and the invoices, and a written list of the planted findings with their expected regions, committed
   before the app's first run.
2. WHEN the generator runs twice with the same seed THE SYSTEM SHALL produce identical files.

## Requirement 7: same skeleton

1. THE SYSTEM SHALL not modify any file under `skeleton/` to build this app; every difference lives in `apps/ghosts/`.
2. THE SYSTEM SHALL use the skeleton's UI kit with this app's region names and columns.
