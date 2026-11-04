# Requirements: the night shift (Kiro Crew job, Kiro power, partition proof)

## Introduction

Night Audit runs every night without a person at the keyboard. This spec covers three pieces that make it native to
Kiro: a Kiro Crew app that runs the audit and investigates what it finds, a Kiro power that lets any Kiro user add a
reconciliation control to their own project, and a machine-checked proof of the matcher's partition law.

## Requirement 1: the Crew nightly job

1. THE SYSTEM SHALL ship `crew/` with the files and the setup command that register a Kiro Crew recurring job named
   `night-audit` at 02:00 UTC that runs `nightaudit run` for each control in `apps/*/controls/`.
2. WHEN the run produces new findings THE SYSTEM SHALL have an investigator crewmate open each new Vampire, Ghost and
   Poltergeist, gather read-only context (CloudTrail creating event, resource tags, the HR record), and append a short
   note to the finding. The note SHALL pass the explanation guard.
3. THE SYSTEM SHALL restrict the investigator to read-only tools through Crew permissions, and the project's
   `read-only-aws` hook SHALL refuse any write call.
4. WHEN the job completes THE SYSTEM SHALL post the morning report summary to the configured channel and keep Crew's
   signed audit log entry for the run.

## Requirement 2: the Kiro power

1. THE SYSTEM SHALL ship `power/night-audit/` as a Kiro power using the current Agent Plugins layout (`plugin.json`,
   `skills/<name>/SKILL.md`, `mcp.json`).
2. THE SYSTEM SHALL include a skill `add-control` that, given three ledger sources in plain words, writes a control file,
   the connectors, fixtures and contract tests, and a casebook of at least five labelled cases before any matcher run.
3. THE SYSTEM SHALL include a skill `read-a-night` that explains a run's findings to a non-specialist, citing only
   evidence values.
4. WHEN the power is installed with `kiro-cli powers install` from the repository THE SYSTEM SHALL work in a project that
   has no other Night Audit files.

## Requirement 3: the partition proof

1. THE SYSTEM SHALL ship `lean/` with a Lean 4 model of region assignment and proofs that, for any finite sets of keys
   in the three ledgers, every key in their union is assigned exactly one region, and that the assignment does not
   depend on record order.
2. THE SYSTEM SHALL ship a differential test that runs the Python matcher and the Lean model's executable region
   function on the same generated inputs and requires identical regions.
3. THE SYSTEM SHALL build the proof in CI and fail the build if any proof is incomplete (`sorry`).
