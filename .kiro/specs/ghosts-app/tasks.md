# Tasks: Ghosts, the access review that reconciles people

Ordered implementation checklist. Each task is small (one module or one test file). Requirement references are in
brackets; property ids refer to design ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â§11. A task is ticked only when its tests pass. Nothing under `skeleton/`
changes [Req 7.1].

## Setup

- [x] **1. Test setup.** `apps/ghosts/tests/conftest.py` registers the hypothesis profile (100 examples, no deadline,
      `derandomize` and no database under `CI`). Test files are named `test_ghosts_*.py` so their module names do not
      collide with the skeleton's or Vampires'. No new dependencies. [tech]

## The control

- [x] **2. Control file.** `apps/ghosts/controls/staff-access.yaml`: three ledgers with `[email_canonical]`, alias
      `hollowpines.org -> hollowpines.com`, `grace_hours: 72`, the seven region names and meanings, the `ui` section
      (noun person/people; ledgers HR roster, Accounts, Paid seats; columns Person, Region, Systems, Seats, Left on,
      Last sign-in, Manager; headlines), and the `people_context` enricher. `test_ghosts_control.py` loads it with the
      skeleton's loader and checks every value. [Req 1.1, 7.2]

## Connectors

- [x] **3. HR roster connector.** `ghosts.connectors.HrRoster` with `belongs_on`, the `today` option and an injected
      clock. Fixture `tests/fixtures/hr_roster.csv`. Contract test through the connector; boundary tests for a
      leaving date at, before and after the run date and a start date at, before and after it. Property G1.
      [Req 2.1, 2.2]

- [x] **4. Identity export connector.** `ghosts.connectors.IdentityExport`: active accounts only, creation time as the
      timestamp, system, status, last sign-in. Fixture and contract test, including a disabled account and a
      malformed timestamp. [Req 3.1]

- [x] **5. Seat assignments connector.** `ghosts.connectors.SeatAssignments`: one keyed record per assignment at the
      invoice unit price, unnamed seats as unkeyed records, latest invoice per vendor, vendor mismatch raises.
      Fixtures and contract tests for over, equal and under invoices. [Req 4.1, 4.2]

- [x] **6. GitHub organisation members connector.** `ghosts.github.GitHubMembers` with an injected `HttpClient` (GET
      only), `UrllibClient`, token from the environment, scope check, org name check, same-host pagination, login to
      email through the roster. Recorded fixture of GitHub's documented `GET /orgs/{org}/members` response (two pages
      with a `Link` header). Ship `controls/staff-access-github.yaml`. [Req 3.2]

## Context and summary

- [x] **7. people_context enricher.** `ghosts.context.people_context`: person, department, manager, left on / leaving
      on / starts on, systems, seats, last sign-in. Tests: a leaver's leaving date reaches the finding's evidence row;
      the control's enricher alias table equals the control's. [Req 2.2, 5.1]

- [x] **8. Seat summary and run command.** `ghosts.seats` (`seat_summary`, `write_seat_summary`) and
      `python -m ghosts.run`. Tests: an invoice below its assignments is reported beside the run with the shortfall;
      property G3. [Req 4.3]

## Demo company and acceptance

- [x] **9. Generator.** `ghosts.generate`: `build_company(seed, plant)`, `write_company`, CLI. Writes
      `apps/ghosts/data/`. Tests: 180 people belong on the run date, every name and vendor is from the fixed pools,
      the planted people match `planted.yaml`, the committed data equals a fresh build. Property G6. [Req 6.1, 6.2]

- [x] **10. Acceptance run.** `ghosts.acceptance` and `test_ghosts_planted.py`: the Hollow Pines run equals
      `planted.yaml` (findings, unnamed seats, informational minimum, counts), with no pending keys and nothing
      extra. [Req 1-4, 6.1]

- [x] **11. Self-attack.** `test_ghosts_self_attack.py`: a healthy company has zero findings (property G5); an alias
      domain plus a `+tag` resolves to the same person (property G2); hostile text in a name changes no region
      (property G4). [audit rule 4, product rules]

## Review campaign

- [x] **12. Review export.** `ghosts.review export`: CSV with formula neutralisation, escaped HTML with its own CSP.
      Property G9. [Req 5.1]

- [x] **13. Review import and verify.** `ghosts.review import` and `verify`: whole-sheet validation, refusal of
      unreported keys with a clear message, hash-chained `decisions.jsonl` seeded with the run's final evidence chain
      hash, tamper detection. Properties G7 and G8. [Req 5.2]

## Demo

- [x] **14. Recorded demo.** `apps/ghosts/demo/build.py` writes the static files of one recorded night and the
      `apps.json` entry. Test: a build into a temporary folder has every file, the evidence verifies, the page reads
      the Ghosts words, and the committed output equals the fresh build. [Req 7.2]

## Verification

- [x] **15. Checks.** `uv run ruff check .`, `uv run mypy apps/ghosts/src`, `uv run pytest apps/ghosts -q` and
      `uv run python -m ghosts.acceptance` pass. `git status` shows no change under `skeleton/`. [Req 7.1, tech]
