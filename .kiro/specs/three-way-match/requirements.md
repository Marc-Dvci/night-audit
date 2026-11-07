# Requirements: the three-way match skeleton

## Introduction

The skeleton (`skeleton/`, package `nightaudit`) runs one reconciliation control over three ledgers (intended, observed,
billed) and produces findings with evidence. Applications supply connectors and a control file. The skeleton owns
normalisation, matching, night-over-night state, the evidence pack, the explanation guard and the API that the UI reads.

## Glossary

- **Record**: one row from one ledger: ledger name, source, row id, raw key, attributes, optional amount, timestamp.
- **Key**: the normalised identifier used to match records across ledgers.
- **Region**: the set of ledgers a key appears in, written as a code (`IOB`, `OB`, `O`, `B`, `I`, `IB`, `IO`).
- **Control file**: YAML that declares the three ledgers, their key fields and normalisers, the grace window, scope
  filters, and the name, severity and wording template of each region.
- **Run**: one execution of a control at a given time.

## Requirement 1: control files

**User story:** As an auditor, I want a control declared in one file, so that the control's logic can be reviewed
without reading code.

1. WHEN a control file is loaded THE SYSTEM SHALL validate it against a schema and reject a file that does not declare
   exactly three ledgers named `intended`, `observed` and `billed`.
2. WHEN a control file names a normaliser that is not registered THE SYSTEM SHALL reject the file and name the
   unknown normaliser.
3. WHEN a control file is loaded THE SYSTEM SHALL compute a SHA-256 hash of its canonical form and attach it to every
   run.
4. WHERE a region is not named in the control file THE SYSTEM SHALL use the default name from the product glossary.

## Requirement 2: normalisation

**User story:** As an auditor, I want the same thing to get the same key in every ledger, so that a mismatch means a
real difference.

1. WHEN a raw key is normalised THE SYSTEM SHALL apply the control's normaliser chain in order and return a string.
2. THE SYSTEM SHALL provide at least these normalisers: `strip`, `lower`, `email_canonical` (lower-case, remove
   `+tag`, map listed alias domains), `arn_resource_id` (reduce an ARN to its resource id), `collapse_whitespace`.
3. WHEN a normaliser is applied twice THE SYSTEM SHALL return the same value as applying it once.
4. WHEN a raw key normalises to an empty string THE SYSTEM SHALL exclude the record from matching and report it in a
   separate "unkeyed" list with its row id.

## Requirement 3: matching

**User story:** As an auditor, I want every key placed in exactly one region, so that nothing is counted twice or lost.

1. WHEN a run matches records THE SYSTEM SHALL assign each key to exactly one region given by the set of ledgers that
   contain it.
2. THE SYSTEM SHALL produce the same regions for the same records regardless of record order.
3. WHEN all three ledgers contain the same set of keys THE SYSTEM SHALL produce zero findings.
4. WHEN a key appears more than once in the same ledger THE SYSTEM SHALL keep every record as evidence and report the
   duplicate count on the finding.
5. WHEN records are matched THE SYSTEM SHALL report, for every region, the count of keys and the sum of billed amounts,
   and the sum over regions plus the unkeyed billed amount SHALL equal the total billed amount of the run.
6. WHEN a run is scored against `casebook/dev/cases.yaml` THE SYSTEM SHALL report, per case, whether regions, pending
   keys, unkeyed rows, finding counts, dropped counts and billed totals equal the expected values.

## Requirement 4: grace window and scope

**User story:** As a CTO, I want late billing data ignored until it can arrive, so that new resources do not raise
false alarms.

1. WHEN an observed record is younger than the control's grace window and its key is absent from the billed ledger THE
   SYSTEM SHALL mark the key as pending instead of producing a finding.
2. WHEN a control declares scope filters THE SYSTEM SHALL drop out-of-scope records before matching and report the
   number dropped per ledger.

## Requirement 5: night-over-night state

**User story:** As an IT manager, I want to see what is new tonight and what has been haunting for weeks, so that I can
prioritise.

1. WHEN a run completes THE SYSTEM SHALL compare its findings with the previous run of the same control and mark each
   finding as `new`, `persisting` or `resolved`.
2. WHEN a finding persists THE SYSTEM SHALL keep its first-seen time and report the number of nights it has persisted.
3. WHEN a run is repeated with identical inputs THE SYSTEM SHALL produce identical findings and identical evidence
   hashes.

## Requirement 6: evidence pack

**User story:** As an external auditor, I want evidence I can verify without trusting the tool, so that I can rely on
the control.

1. WHEN a run completes THE SYSTEM SHALL write an evidence pack: one JSON Lines file of evidence rows, each row carrying
   the SHA-256 of the previous row, and a manifest with the control hash, each ledger snapshot hash, record counts and
   the final chain hash.
2. WHEN `nightaudit verify <pack>` is run THE SYSTEM SHALL recompute the chain and report the first row that does not
   verify, or confirm the whole pack.
3. WHEN any byte of an evidence row is changed THE SYSTEM SHALL fail verification.

## Requirement 7: explanations

**User story:** As a CTO, I want each finding explained in one or two plain sentences, so that I can act on it without
reading raw rows.

1. WHEN a finding is explained THE SYSTEM SHALL send the model only the region, the region meaning and the finding's
   evidence fields, each quoted and truncated to 200 characters.
2. WHEN the model's text contains a number that does not appear in the finding's evidence THE SYSTEM SHALL discard the
   text, use the deterministic template, and record the rejection.
3. IF the model is unavailable or times out after 10 seconds THEN THE SYSTEM SHALL use the deterministic template.
4. WHEN an evidence field contains text that looks like an instruction THE SYSTEM SHALL treat it as data, and the
   finding's region SHALL be the same as without that text.

## Requirement 8: API and UI kit

**User story:** As a CTO, I want one screen that shows tonight's three ledgers and what does not match, so that the
morning check takes a minute.

1. THE SYSTEM SHALL serve `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/findings?region=` and
   `GET /api/runs/{id}/evidence.zip`.
2. WHEN the UI loads a run THE SYSTEM SHALL draw a three-circle Venn diagram whose regions show their key counts, and
   selecting a region SHALL filter the findings list to that region.
3. THE SYSTEM SHALL show each finding as a row with its monster name in words, its key, its nights persisted, its
   billed amount and its explanation.
4. THE SYSTEM SHALL pass an automated WCAG 2.2 AA scan on every screen.

## Requirement 9: connectors

**User story:** As a developer, I want to add a ledger source by writing one small class, so that the skeleton serves
new controls.

1. THE SYSTEM SHALL define a connector interface that returns records for one ledger and declares whether it is
   read-only.
2. WHEN a connector declares that it is not read-only THE SYSTEM SHALL refuse to run it.
3. THE SYSTEM SHALL provide a CSV connector and a JSON Lines connector usable by any app.
4. WHEN a connector fails THE SYSTEM SHALL mark the run as incomplete, name the ledger, and produce no findings that
   depend on the missing ledger.

## Requirement 10: What the second app taught

**User story:** As the author of a second application, I want the skeleton to give me what I had to work around, so
that the next application needs no workaround at all.

Source: `.kiro/specs/ghosts-app/design.md` §10, the gaps the staff access app met while it could not change the skeleton.

1. WHEN a run fetches a ledger THE SYSTEM SHALL give every connector the run's time through the `Connector` base class
   before `fetch()` is called, and a connector that does not read the run time SHALL need no change.
2. WHERE a control declares `summarisers` THE SYSTEM SHALL add each summariser's sentences to the run as `notes`, write
   them into the evidence chain, and show them under the headline on the page and in the morning report; IF a note
   cites a number that does not appear in the run's evidence rows THEN THE SYSTEM SHALL refuse that summariser's notes
   and name the summariser in the run's errors.
3. WHEN the system calls an enricher or a summariser that accepts a `control` argument THE SYSTEM SHALL pass the
   control file's folder, its alias domains, its id and the run time.
4. WHERE a control declares `ui.unkeyed` THE SYSTEM SHALL use its `singular`, `plural` and `explanation` for the
   billed lines with no key on the page and in the morning report, and SHALL otherwise use the wording used before
   this requirement.
5. WHEN a region template contains `{context:<name>}` or `{attr:<name>}` THE SYSTEM SHALL fill it from the finding's
   context or the first record carrying that attribute, render an absent value as empty text without failing, and use
   the default template IF the rendered text cites a number that is not in the finding's evidence.
6. WHERE a control declares `ui.downloads` THE SYSTEM SHALL link each listed file that exists in the run's folder from
   the page, serve it from the API and copy it into the static demo, and SHALL refuse any file name outside a strict
   allow-list, so that no request can read a file outside the run's folder.
7. WHEN a run's evidence folder holds a decision chain (`decisions.jsonl`) THE SYSTEM SHALL show each decision with its
   reviewer and date on the finding it names, only after the chain verifies against the run's final evidence hash, and
   SHALL otherwise say that the recorded decisions do not verify and show none.
8. WHEN the static demos are built THE SYSTEM SHALL write each application's demo only into its own folder under
   `skeleton/web/public/demo/<app>/`, list every live and demo entry in `apps.json`, and keep the `?demo=1` link
   working.
