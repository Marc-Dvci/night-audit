# Requirements: the night ledger UI kit

## Introduction

`skeleton/web/` is the shared front end of every Night Audit app. A visitor arrives with no context, often from a judge's
link or a morning email, and has to understand what they are looking at within ten seconds. Every word that differs
between apps comes from the control file, so a second app needs no change to the skeleton. The look is the green-bar
night ledger of `.kiro/steering/ui-identity.md`.

Users: a startup CTO at 08:30 who wants to know whether anything needs them today, and an IT manager preparing an access
review that an auditor will test.

## Glossary

- **Vocabulary**: the words a control supplies for its ledgers, the things it counts, and its headline.
- **Headline**: one sentence stating tonight's result, computed by code from the run.
- **Night**: one run of a control.

## Requirement 1: the control supplies the words

1. THE SYSTEM SHALL accept an optional `ui` section in a control file with: `title`, `tagline`, `noun` (`singular` and
   `plural`), `ledgers` (for each of intended, observed and billed: a short `label` and a `source` sentence), `columns`
   (an ordered list of `{label, from}`, where `from` is `key`, `name`, `status`, `amount`, `attr:<name>` or
   `context:<name>`), and `headlines` (a template per region code with `{count}`, `{amount}` and `{noun}` slots).
2. WHEN a control has no `ui` section THE SYSTEM SHALL use neutral defaults, and the page SHALL still render.
3. THE SYSTEM SHALL copy the resolved `ui` values into the run result, and include them in the control hash, so that a run
   renders the same way forever, even after the control file changes.
4. THE SYSTEM SHALL ship the `ui` section for `apps/vampires/controls/aws-account.yaml` and for the Vampires demo controls.

## Requirement 2: the first ten seconds

1. WHEN a run is shown THE SYSTEM SHALL show, above the Venn diagram, the control's tagline and the headline.
2. THE SYSTEM SHALL compute the headline in Python in `skeleton/src/nightaudit/report.py` from the region summaries of the
   run. Regions with no findings are omitted. Every number in it comes from the run. Example: "3 Vampires are running and
   on the bill with no approval: $0.59 so far. 2 Poltergeists cost nothing. 1 declared resource is gone."
3. WHEN a complete run has zero findings THE SYSTEM SHALL state "All three ledgers agree. Nothing to report tonight." as
   the headline, and the page SHALL read as a calm, finished state, with no empty-looking regions.
4. THE SYSTEM SHALL show each ledger's label, its `source` sentence and its count of distinct keys beside the Venn
   diagram, so a visitor sees what is being compared.
5. THE SYSTEM SHALL count keys, not rows, in the Venn labels. Rows with no key are never counted there.
6. WHEN a region filter is active THE SYSTEM SHALL show that region's name and meaning above the rows.
7. THE SYSTEM SHALL print an amount in the headline rounded half-even to four significant figures, never coarser than a
   cent (`$0.7172` for `0.7172358001`, `$0.7172` for `0.71725`), in Python and TypeScript alike. The table, the money lines,
   the page data and the evidence SHALL keep the exact amount.

## Requirement 3: money that reads true

1. THE SYSTEM SHALL show the billed total of keyed, in-scope lines as the headline amount, labelled for the control's noun.
2. THE SYSTEM SHALL show lines with no key (credits, tax, support) on their own line with their own label, never summed into
   the headline amount. A negative number there is expected and SHALL be explained in words.
3. THE SYSTEM SHALL keep the three amounts conserved: keyed total + unkeyed total = billed total of the run.
4. THE SYSTEM SHALL not break a word in the middle in any summary line, at any viewport width from 360 px.

## Requirement 4: the nights

1. THE SYSTEM SHALL show a strip of the most recent nights of the control (up to 30), one mark per night, with its finding
   count and new-finding count visible by text as well as by mark height. Selecting a mark opens that night.
2. WHEN a finding has persisted THE SYSTEM SHALL show since when, with the date of `first_seen`.
3. WHEN findings were resolved since the previous night THE SYSTEM SHALL list them in a section titled "Laid to rest" with
   the region, the key, the date first seen and the nights it lasted.

## Requirement 5: deep links

1. THE SYSTEM SHALL support `?app=`, `?run=`, `?region=` and `?open=<key>` query parameters, keep them in the URL as the
   reader navigates, and open the named finding and scroll to it on load.
2. WHEN a query parameter names something absent from the run THE SYSTEM SHALL ignore it and show the run.

## Requirement 6: check the chain yourself

1. THE SYSTEM SHALL offer a "Verify this night" action that downloads `evidence.jsonl` and `manifest.json` for the run and
   recomputes the whole hash chain in the browser with WebCrypto, using the same canonical JSON as
   `skeleton/src/nightaudit/evidence.py` (sorted keys, compact separators, non-ASCII escaped as `\uXXXX`).
2. WHEN verification succeeds THE SYSTEM SHALL state the row count, the finding count and the final hash, and that the hash
   matches the manifest and the hash shown on the page.
3. THE SYSTEM SHALL offer a "Change one byte" action that alters one character of one row, in memory only, re-runs the
   verification and shows the first row that fails, then a way to restore the original.
4. THE SYSTEM SHALL produce the same verdict as `nightaudit verify` on the same pack. A test SHALL compare the browser
   implementation with the Python implementation on a pack containing hostile unicode, including bidi overrides,
   astral-plane characters and quotes.
5. THE API SHALL serve `GET /api/runs/{id}/evidence.jsonl` and `GET /api/runs/{id}/manifest.json`, and demo mode SHALL ship
   the same files statically.
6. WHEN the page is verified THE SYSTEM SHALL compare what the page shows with the chain, and take whether the night was
   complete from the chain's header row, never from the page. A pack written before the header recorded completeness
   SHALL count as incomplete only when it holds no finding row and a ledger with no record row.
7. THE SYSTEM SHALL accept an amount in the headline text only when it is a headline region's amount in the chain, written
   exactly or rounded as Requirement 2.7 rounds it. Every other figure on the page SHALL equal the chain exactly.

## Requirement 7: the morning report

1. THE SYSTEM SHALL produce a one-page HTML report for each run from `skeleton/src/nightaudit/report.py`: control, night,
   headline, counts per region, new findings first, the billed amount of each billed finding, nights persisted, resolved
   findings, the evidence chain hash. It is self-contained (no external requests) and prints on one A4 page for a run of up
   to 12 findings, on a white ground with faint green bars, like the printout it is named after.
2. THE API SHALL serve it at `GET /api/runs/{id}/report.html`, the UI SHALL link to it from the masthead, and demo mode SHALL
   ship it statically.
3. THE SYSTEM SHALL escape every ledger value in the report. A test SHALL plant a script payload in a ledger value and assert
   that it appears only as text.
4. A test SHALL assert that every number in the report's headline and table exists in the run.

## Requirement 8: more than one app

1. THE SYSTEM SHALL offer a switch in the masthead between the apps available to this deployment. The available apps come
   from `apps.json` (name, title, `live` or `demo`, base path), written at build time.
2. WHEN an app's control declares `columns` THE SYSTEM SHALL render the finding rows with those columns, in that order.
3. THE SYSTEM SHALL show recorded (synthetic) runs as such, in words, in the masthead. A recorded run is never presented as
   live data.

## Requirement 9: link card and first impression

1. THE SYSTEM SHALL ship a page title, a meta description, a favicon as SVG, and Open Graph and Twitter card tags with an
   image of 1200 by 630 pixels that is a real capture of the product with its name on it.
2. THE SYSTEM SHALL serve the page with no layout shift when fonts arrive, and no request to a third party.

## Requirement 10: accessibility and phones

1. THE SYSTEM SHALL meet WCAG 2.2 AA on every screen state, checked by axe-core in a browser test that fails on any
   violation.
2. THE SYSTEM SHALL offer every action by keyboard, with a visible phosphor focus ring and a skip link.
3. THE SYSTEM SHALL have no horizontal page scroll at 360 px. Evidence tables scroll inside their own container.
4. THE SYSTEM SHALL respect `prefers-reduced-motion`.

## Requirement 11: every value is untrusted

1. THE SYSTEM SHALL render every value from a ledger as text. A browser test SHALL open a finding whose name is a script
   payload and assert that no dialog opens and the payload is visible as text.
2. THE SYSTEM SHALL send a Content-Security-Policy that allows only same-origin scripts, styles, fonts and images, from the API
   and in the Lambda deployment.

## Requirement 12: browser tests

1. THE SYSTEM SHALL ship Playwright tests under `skeleton/tests/e2e/`, marked `e2e`, that drive every screen state of the demo
   path in headless Chromium against a local server: overview, each region filter, an opened finding, a deep link, the nights
   strip, verify, change one byte, the report, a clean night, a phone viewport.
2. THE SYSTEM SHALL run axe-core in those tests with the WCAG 2.0, 2.1 and 2.2 A and AA rules.
