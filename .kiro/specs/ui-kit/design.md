# Design: the night ledger UI kit

## 1. Overview

`skeleton/web/` is the front end every Night Audit app shares. It reads one run and answers, in this order: what is
being compared, what tonight's result is, where the findings are, and how to check the result yourself. Every word that
differs between apps comes from the control file's `ui` section (Req 1), copied into the run so an old night renders as
it did.

The page is a night-shift printout, not a dashboard:

- No cards, no bordered boxes, no rounded panels, no gradients except the masthead scan line. Structure comes from bands
  of `ink` and `ink-2` and from hairline `phosphor` rules.
- `IBM Plex Mono` for anything a machine printed (keys, amounts, dates, hashes, counts, labels in capitals).
  `IBM Plex Sans` for sentences a person reads (headline, tagline, meanings, explanations).
- After the masthead, the headline is the largest text on the page: sans, about 2.6rem on desktop, at most 34ch wide.
- The Venn diagram stays the main navigation. The legend beside it is the keyboard path to the same filter.
- `blood` is used only for a finding with `nights_persisted > 3`. `amber` marks a finding that is new tonight.

Code decides every word that carries a number. `report.py` computes the headline and the summary lines in Python; the
browser displays those strings and the decimal strings the API sends. The browser never computes money.

## 2. Module map

```
skeleton/
  src/nightaudit/
    control.py        + UiConfig, LedgerUi, ColumnUi, NounUi, HeadlineUi; ControlFile.ui; resolve_ui()
    models.py         + RunResult.ui (resolved UiConfig), RunResult.control_id stays
    report.py         NEW: money_text, headline, run_view, run_numbers, report_html
    evidence.py       + VerifyResult.failed_row; canonical_json made public
    runner.py         + copies resolved ui into the run; run_summary gains new_findings
    api.py            + evidence.jsonl, manifest.json, report.html routes; CSP middleware; run JSON gains "view"
  web/
    index.html        title, description, OG/Twitter tags, favicon.svg, skip link (CSP meta added at build)
    public/
      favicon.svg
      og.png          1200x630 capture of the demo, written by scripts/capture_card.py
      apps.json       written by the demo build
    src/
      main.ts         entry: load apps.json, read query, wait for fonts, load run, render, delegate events
      fonts.css       self-hosted Plex (latin subset from @fontsource), font-display: block
      api.ts          data access for live and demo mode (same file names in both)
      state.ts        URL <-> state (app, run, region, open)
      format.ts       esc(), moneyText() string-only, dates
      canonical.ts    canonical JSON identical to Python json.dumps(sort_keys, separators, ensure_ascii)
      verify.ts       WebCrypto chain verification (shipped as the stable chunk assets/verify.js)
      render/
        masthead.ts   brand, app switch, recorded-run notice, run picker, report link
        lede.ts       tagline + headline + money lines
        venn.ts       SVG Venn (moved), ledger labels with source sentence and key count
        legend.ts     region legend (keyboard path to the filter)
        nights.ts     nights strip
        rows.ts       finding rows driven by ui.columns, evidence table, "Laid to rest"
        verify.ts     line-printer output of the verify action, change one byte, restore
      glyphs.ts       unchanged
      types.ts        + UiConfig, RunView, AppEntry
      style.css       rewritten
    test/
      canonical.test.ts, verify.test.ts, format.test.ts
      fixtures/parity.json    written by scripts/write_parity_fixture.py
    vitest.config.ts
  tests/
    test_report.py                       unit tests (boundaries)
    test_ui_config.py                    control ui section
    test_api_ui.py                       new routes, CSP header, report escaping
    test_property_headline_numbers.py    P11
    test_property_money_text.py          P13
    test_property_report_escaping.py     P14
    test_parity_fixture.py               the committed vitest fixture is up to date
    e2e/
      conftest.py        build check, local server on a free port, headless Chromium, axe helper
      test_screens.py    every screen state + axe (Req 10, 12)
      test_property_verify_parity.py     P15
      test_layout.py     360 px, no word breaks, no layout shift, A4 report
scripts/
  write_parity_fixture.py
  capture_card.py        og.png and the review screenshots
apps/vampires/demo/build.py   + evidence files, report.html, view-augmented run JSON, apps.json
```

## 3. The `ui` section (Req 1)

### Schema

```yaml
ui:
  title: Vampires
  tagline: Every night, the account is checked against what was approved and what is on the bill.
  noun: {singular: resource, plural: resources}
  ledgers:
    intended: {label: Declared, source: CloudFormation stacks and approved changes.}
    observed: {label: Running, source: Live inventory from read-only Describe and List calls.}
    billed:   {label: Billed, source: Cost and Usage Report 2.0 line items.}
  columns:
    - {label: Resource, from: key}
    - {label: Kind, from: "attr:kind"}
    - {label: Region, from: "attr:region"}
    - {label: Created by, from: "context:created_by"}
    - {label: Since, from: status}
    - {label: On the bill, from: amount}
  headlines:
    OB: {one: "{count} Vampire is running and on the bill with no approval: {amount} so far.",
         other: "{count} Vampires are running and on the bill with no approval: {amount} so far."}
    O:  "{count} Poltergeist {noun} cost nothing."   # a plain string is used for both forms
```

| Model | Fields |
|---|---|
| `NounUi` | `singular: str`, `plural: str` |
| `LedgerUi` | `label: str`, `source: str` |
| `ColumnUi` | `label: str`, `from_: str` (alias `from`), validated against `key`, `name`, `status`, `amount`, `attr:<name>`, `context:<name>` |
| `HeadlineUi` | `one: str`, `other: str`. A plain string in YAML becomes both |
| `UiConfig` | `title`, `tagline`, `noun`, `ledgers: dict[str, LedgerUi]`, `columns: list[ColumnUi]`, `headlines: dict[str, HeadlineUi]` |

**Plural forms.** Req 1.1 names a template per region with `{count}`, `{amount}` and `{noun}` slots. English needs a
singular and a plural sentence ("1 Vampire is", "3 Vampires are"), so a template is a `{one, other}` pair; a plain string
is accepted as shorthand. `{noun}` resolves to `noun.singular` when the count is 1 and `noun.plural` otherwise. This is an
interpretation of Req 1.1 and is flagged in the task list.

Templates are validated on load: only the three slots are allowed, and a template must contain `{count}`. A headline
template is control text (trusted, version-controlled), never ledger text.

### Defaults (Req 1.2)

`resolve_ui(control_file)` fills every missing field:

| Field | Default |
|---|---|
| `title` | `control.title` or `control.id` or "Night Audit" |
| `tagline` | "Three ledgers of the same reality, matched every night." |
| `noun` | `item` / `items` |
| `ledgers` | Intended / "What was approved."; Observed / "What exists."; Billed / "What is paid for." |
| `columns` | `key`, `status`, `amount` |
| `headlines` | per finding region, built from the region's resolved name, for example `{count} {name} {noun}` + the region's fixed sentence (table below) |

Default headline sentences (the region name comes from `resolve_region`, so a control that renames OB to Ghost gets
"Ghost" without writing a headline):

| Code | one | other |
|---|---|---|
| OB | `{count} {name} {noun} exists and is on the bill with no approval: {amount}.` | `... {noun} exist and are on the bill ...` |
| B | `{count} {name} line is on the bill for something nobody approved or can see: {amount}.` | `lines are` |
| IB | `{count} {name} {noun} is approved and billed but cannot be seen: {amount}.` | `are` |
| I | `{count} approved {noun} is gone.` | `are gone.` |
| O | `{count} {name} {noun} exists with no approval and no charge.` | `exist` |

`{name}` is resolved by code before formatting and is not offered to control authors as a slot.

### Run copy and hash (Req 1.3)

`ControlFile.ui: UiConfig | None` is part of `ControlFile.model_dump`, so it is already inside
`ControlFile.canonical_hash()`. The runner stores `resolve_ui(control_file)` in `RunResult.ui`. Rendering reads only
`RunResult.ui`, never the control file, so a run renders the same forever. A run saved before this change has no `ui`;
`RunResult.ui` defaults to the neutral `UiConfig()` so it still loads and renders.

## 4. `report.py` (Req 2, 3, 7)

Pure functions of a `RunResult`. No clock, no I/O except `report_html` returning a string.

### `money_text(value: Decimal) -> str`

Exact display of a decimal with no rounding, so every displayed amount is a number of the run (audit rule 2):

1. `-0` and any zero become `$0.00`. A negative value gets the minus sign U+2212 before the `$`.
2. The value is written in fixed point (`format(value, "f")`, so `1E+5` becomes `100000`).
3. The fraction keeps at least two digits and every significant digit beyond that: `0.5` → `0.50`,
   `0.123456789` → `0.123456789`, `41.200` → `41.20`.
4. The integer part is grouped in threes with commas.

TypeScript `moneyText(s: string)` implements the same rules on the decimal string, character by character, with no
`Number()`. A shared fixture (P13, §8) holds the expected output for both.

### `ledger_key_counts(run) -> dict[str, int | None]`

Distinct non-null keys per snapshot; `None` for a missing ledger (Req 2.4, 2.5). Unkeyed rows are never counted.

### `headline(run) -> str` (Req 2.2, 2.3)

1. Missing ledgers: "The {labels} ledger could not be read, so tonight has no findings." (labels from `ui.ledgers`,
   joined with "and"). Contains no number.
2. Complete with zero findings (informational `IO` keys do not count):
   "All three ledgers agree. Nothing to report tonight."
3. Otherwise one sentence per finding region in the order `OB, B, IB, O, I` (billed regions first, then unbilled, as in
   the Req 2.2 example), omitting regions with no keys. `{count}` is
   the region's `key_count`, `{amount}` is `money_text(region_summaries[code].billed_amount)`, the `one` template is used
   when the count is 1.

### `run_view(run) -> RunView`

Everything the page and the report show that is derived from the run, computed once in Python:

| Field | Value |
|---|---|
| `headline` | `headline(run)` |
| `calm` | complete and zero findings |
| `ledger_keys` | `ledger_key_counts(run)` |
| `keyed_total` | `billed_total - billed_unkeyed` as a decimal string (Req 3.1) |
| `unkeyed_total` | `billed_unkeyed` as a decimal string |
| `billed_total` | `billed_total` as a decimal string |
| `lines` | the printed summary lines as `{label, value, note}`: "On the bill for {n} {noun}", "No resource id (credits, tax, support)", with the note "A negative amount here is a credit." when `billed_unkeyed < 0` (Req 3.2) |
| `new_count`, `persisting_count`, `pending_count` | counts |

`keyed_total + unkeyed_total == billed_total` holds by construction and is asserted (Req 3.3). The API adds `view` to the
run JSON; demo mode ships the same JSON.

### `run_numbers(run) -> set[Decimal]`

The numbers a run contains: every key count, ledger key count, region amount, finding amount, record amount,
`nights_persisted`, the three totals, counts of new/persisting/pending/resolved/findings, and the day, month number and
year of `run_time` and of every `first_seen`. Tests use it as the oracle for "every number comes from the run" (Req 2.2,
7.4). It is not used to filter output; output is built only from these values.

### `report_html(run, recorded: bool = False) -> str` (Req 7.1)

One self-contained page: a single inline `<style>`, no scripts, no external URL, inline SVG glyph-free (text only). White
ground, faint green bars (`#E8F5EC` every other row), Plex is not embedded (it would be 200 kB); the report uses
`ui-monospace` and `system-ui` stacks.

Content, in order: control title and night, headline, counts per region (the seven codes with names), findings table
(new first, then by region order, then key) with columns region name, key, status ("new" or "since 04 Nov 2026, 2
nights"), billed amount; "Laid to rest" table; the money lines; evidence chain hash and control hash. `@page { size: A4;
margin: 12mm }` and compact type so 12 findings fit one page.

Every ledger value goes through `html.escape(value, quote=True)` (Req 7.3). Control text (`ui`) is escaped too. The only
markup is built from fixed strings in `report.py`.

## 5. Evidence for the browser (Req 6)

### Python changes

- `canonical_json` becomes public (same function: `json.dumps(obj, sort_keys=True, separators=(",", ":"))`, which uses
  `ensure_ascii=True`).
- `VerifyResult` gains `failed_row: int | None` (the 0-based row index of the first failure, `None` for a manifest-level
  failure or success) and `rows: int`, `findings: int`, `final_hash: str | None`. `detail` text is unchanged so the CLI
  and existing tests keep working.

### Canonical JSON in TypeScript (`canonical.ts`)

`JSON.stringify` differs from Python in three ways that matter, so the encoder is written by hand:

| Concern | Python (`ensure_ascii=True`) | TypeScript rule |
|---|---|---|
| Non-ASCII | `\uXXXX` lowercase hex, astral as a surrogate pair | escape every UTF-16 code unit > 0x7E as `\u` + 4 lowercase hex |
| Control characters | `\n \r \t \b \f`, others `\u00XX` | same table |
| `"` and `\` | `\"` `\\` | same; `/` and 0x7F are not escaped |
| Key order | sorted by code point | sort by code point (`codePointAt` walk), not UTF-16 code units: a key holding U+FFFF must sort before one holding U+10000 |
| Integers | `123` | `String(n)` for safe integers; the rows hold only `index` as a number |
| `null`, booleans | `null`, `true` | same |

### Verification (`verify.ts`)

`verifyPack(jsonlText, manifest, onRow?)` mirrors `verify_evidence_pack` step for step: split on `\n` and drop one
trailing empty line, parse each line, require `canonical(row) === line` (byte-exact), recompute
`sha256(prev_hash + canonical(row without row_hash))` with `crypto.subtle.digest`, check the link to the previous row,
compare the final hash with the manifest, recompute each ledger hash and count, check the finding count. It returns
`{ok, failedRow, detail, rows, findings, finalHash}`. `onRow(index)` is called after each row so the UI can print it.

The function is built as the stable chunk `assets/verify.js` (Vite `manualChunks` + `chunkFileNames`), so the e2e
property test (P15) imports the exact shipped code with `import("./assets/verify.js")`.

### The verify screen (Req 6.2, 6.3)

The action prints in monospace under the footer rule, like a line printer:

```
VERIFY 2026-11-06  downloading evidence.jsonl, manifest.json
ROW 000  record   intended  us-east-1/shop/Web            9f2c41…  OK
ROW 001  record   intended  us-east-1/shop/WebRoot        1b07e3…  OK
...
VERIFIED  27 rows, 8 findings. Final hash 5be1…c09a matches the manifest and the hash on this page.
```

Rows are appended in batches on `requestAnimationFrame` (no timers), so the count visibly climbs. With
`prefers-reduced-motion: reduce` only the final line is printed. The final line is in an `aria-live="polite"` region; the
row lines are `aria-hidden` so a screen reader hears one sentence.

"Change one byte" picks the middle record row, replaces one character inside its `raw_key` value with a different
character of the same width (in memory only), re-runs verification and prints "FAILED at row 012: hash mismatch". The
changed character is shown before and after. "Restore the original" re-runs verification on the untouched text.

### API and demo files (Req 6.5)

`GET /api/runs/{id}/evidence.jsonl` (`application/x-ndjson`) and `GET /api/runs/{id}/manifest.json`. Demo mode ships
`demo/{id}/evidence.jsonl`, `demo/{id}/manifest.json` and `demo/{id}/report.html`; `api.ts` maps the same names.

## 6. The page

### Layout, top to bottom

| Band | Content | Type |
|---|---|---|
| Masthead | `NIGHT AUDIT`, app switch, "Recorded run, synthetic account" for demo apps, night picker, "Morning report" link, scan line | mono |
| Lede | tagline (sans, bone-dim), headline (sans, largest after masthead), money lines (mono, printout bands) | sans + mono |
| Ledgers + Venn | three ledger entries (label in mono caps, source sentence in sans, key count in mono) beside the Venn; legend under it | mixed |
| Nights | strip of up to 30 marks, each a button with its date, findings and new findings as text | mono |
| Filter note | when a region is active: glyph, name, meaning, "Show all findings" | sans |
| Rows | finding rows on alternating bands, columns from `ui.columns` | mono values, sans explanation |
| Laid to rest | resolved findings: region, key, first seen, nights lasted | mono |
| Footer | evidence chain hash, control hash, run id, "Verify this night", "Download the evidence pack" | mono |

Desktop (≥ 1024 px): Venn and ledger entries side by side under the lede; rows full width. Phone (360–430 px): one column,
Venn at full width, ledger entries under it, rows stack each cell as `LABEL value` lines.

### Calm state (Req 2.3)

When `view.calm`: the headline is in phosphor, the Venn shows only the `IOB` count with the other regions unlabelled
instead of a ring of zeros, the rows section reads "{n} {noun} appear in all three ledgers." with the matched keys, and the
legend is hidden. No "0" counts are printed for empty regions.

### Nights strip (Req 4.1)

Data: `/api/runs` filtered to the current `control_id`, newest 30, shown oldest to newest. Each mark is a `<button>` whose
bar height is proportional to the finding count (CSS class `h-0` … `h-10`, so no inline style is needed under the CSP),
with a text label below: `06 NOV` and `8 · 2 new`. The current night has `aria-current="date"`. Selecting a mark loads
that run and updates `?run=`.

### Rows (Req 4.2, 8.2)

Each row is a `<li>` band with a disclosure `<button>` holding the columns in `ui.columns` order. Column sources:

| `from` | Value |
|---|---|
| `key` | `finding.key` |
| `name` | glyph + region name in words |
| `status` | "New tonight" (amber) or "Since 04 Nov 2026 · 2 nights" (bone; blood when `nights_persisted > 3`) |
| `amount` | `moneyText(finding.billed_amount)` |
| `attr:<n>` | first record of the finding with attribute `n`, in ledger order intended, observed, billed |
| `context:<n>` | `finding.context[n]` |

The region name always appears: if `ui.columns` has no `name` column, the name is printed above the columns. The
explanation is a sans paragraph under the columns. The evidence table opens below and scrolls inside its own container
(`overflow-x: auto`) (Req 10.3).

### Deep links (Req 5)

`state.ts` reads `app`, `run`, `region`, `open` and writes them back with `history.replaceState` on every change. Rules:
an unknown `app` is ignored; an unknown `run` falls back to the newest run; a `region` that is not one of the seven codes
is dropped; an `open` key that is not a finding of the run is dropped. After the first render with a valid `open`, the row
is expanded and scrolled into view (instant when reduced motion is set).

### Apps (Req 8.1, 8.3)

`apps.json`: `[{"name": "vampires", "title": "Vampires", "mode": "demo", "base": "./"}]`, written by the demo build and
by any deployment build. The masthead shows a `<select>` when there are two or more apps and a plain label otherwise.
A `demo` app prints "Recorded run · synthetic account" next to its title, always in words.

### Untrusted values (Req 11)

Every ledger value is passed through `esc()` before entering markup, and attribute values are quoted. No `innerHTML` is
built from un-escaped run data. CSP (§7) is the second line: even a missed escape cannot run inline script.

### Motion (Req 10.4)

The scan line sweeps once when a run renders. With reduced motion: no scan line, no verify row animation, instant
scrolling.

## 7. Delivery

### Content-Security-Policy (Req 11.2)

A middleware in `create_app` adds to every response:

```
default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self';
connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

plus `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`. `report.html` gets its own policy with
`style-src 'sha256-<hash of its style block>'` and no `script-src`. `deploy/handlers.py` builds the Lambda app with
`create_app`, so the deployment gets the header without a change under `deploy/`. Static demo hosting cannot send
headers, so `index.html` also carries the policy in a `<meta http-equiv>` (without `frame-ancestors`, which meta cannot
set).

Consequences for the markup: no inline `<script>`, no `style=""` attributes, the favicon is a file, not a `data:` URL.

### Fonts without layout shift (Req 9.2)

Plex Sans 400/600 and Plex Mono 400/600, latin subset woff2, bundled by Vite from `@fontsource` through
`src/fonts.css`, which declares `font-display: block`. `main.ts` waits for `document.fonts.load` of the four faces
(alongside the data requests) before it draws the page, so text is laid out once, in its final font. The e2e test
records `layout-shift` entries and requires their sum to be 0.

### Link card (Req 9.1)

`<title>Night Audit · three-way match for what you pay for</title>`, meta description, `favicon.svg` (the three rings),
`og:title`, `og:description`, `og:image` = `og.png` (1200×630), `og:image:alt`, `twitter:card=summary_large_image`.
`scripts/capture_card.py` starts the demo server, captures the demo overview at 1200×630 with the name in the masthead,
and writes `public/og.png`. It is a real capture, regenerated when the look changes.

## 8. Testing

### Python unit tests

- `test_ui_config.py`: a control with a full `ui` section loads; one without renders neutral defaults; a bad column
  `from` and a template with an unknown slot are rejected; `ui` changes the control hash; the run carries the resolved ui.
- `test_report.py` boundaries: zero findings (calm sentence), one finding (singular noun and verb), a run with a missing
  ledger (names the ledger, no number), amounts with many decimals (`0.000000001`, `1E+5`, `-0`), unkeyed negative totals
  (printed with U+2212 and the credit note, not summed into the keyed total), region order, omitted empty regions,
  informational `IO` never in the headline.
- `test_api_ui.py`: the evidence files, the manifest and the report are served; unknown run ids 404; every response has
  the CSP header; a planted `<script>` in a ledger value appears in `report.html` only as escaped text (Req 7.3); every
  number in the report headline and table is in `run_numbers` (Req 7.4).
- `test_parity_fixture.py`: regenerating `skeleton/web/test/fixtures/parity.json` gives the committed bytes.

### Vitest (`npx vitest run` in `skeleton/web`)

- `canonical.test.ts`: every case in `parity.json` (`value` → Python `canonical`) matches; key ordering by code point;
  lone surrogates; bidi overrides (U+202E, U+2066); astral characters; quotes and backslashes; control characters.
- `verify.test.ts`: the hostile pack in `parity.json` verifies with the same row count, finding count and final hash as
  Python; each tampered variant fails at the same row Python reports.
- `format.test.ts`: `moneyText` matches Python `money_text` for every case in `parity.json`; `esc` escapes the five
  characters.

Node 20+ provides `crypto.subtle`, so the same `verify.ts` runs under vitest and in the browser.

### Browser tests (`skeleton/tests/e2e/`, marker `e2e`)

`conftest.py` builds nothing: it requires `skeleton/web/dist/index.html` (built by `npm run build`) and skips with a
message if absent. It builds a demo runs folder in `tmp_path_factory` by running the three demo nights plus one clean
night and one hostile night, starts `uvicorn` with `create_app` in a thread on a free port (`port=0`), launches headless
Chromium once per session, and injects `skeleton/web/node_modules/axe-core/axe.min.js` with `page.add_script_tag`.
`assert_axe_clean(page)` runs `axe.run` with tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` and fails on any
violation, printing the rule ids and targets.

No sleeps: waits are on DOM state (`page.wait_for_selector`, `expect`-style polling on text).

| Test | State |
|---|---|
| overview | headline, ledgers with counts, Venn, rows; axe |
| each region filter | click each Venn region and each legend item; filter note shows name and meaning; URL has `region`; axe |
| opened finding | Enter on a row; evidence table; axe |
| deep link | `?run=…&region=OB&open=<key>` opens and scrolls; nonsense parameters are ignored |
| nights strip | select the first night; URL `run` changes; text counts visible |
| verify | final line has rows, findings and the hash shown on the page; with reduced motion only one line exists |
| change one byte | failing row printed; restore verifies again |
| report | link opens, one A4 page via `page.pdf`, no external requests |
| clean night | calm sentence, no zero labels in the Venn |
| phone | 390 px and 360 px: no horizontal scroll, summary words unbroken; axe |
| hostile | a finding named `<img src=x onerror=alert(1)>` shows as text; no dialog event |
| keyboard | skip link first; every action reachable by Tab; focus ring visible (computed outline colour is phosphor) |
| fonts | layout-shift sum is 0 |

Screenshots at 1440 and 390 px for review are written by `scripts/capture_card.py --review` into `build/screens/`
(gitignored), not by the test suite.

## 9. Correctness properties

Each property is a hypothesis test (100 examples, `derandomize` in CI), marked `@pytest.mark.property`, named
`test_property_*`. P15 is also marked `e2e`.

### P11: headline numbers come from the run (validates Req 2.2, 2.3, 7.4)

For any run produced by `match` on hostile snapshots (the generators in `tests/hostile.py`), with any number of findings
and with or without a missing ledger, every number in `headline(run)` and in the report's headline and table is in
`run_numbers(run)`; a region with no keys is not mentioned; the singular template is used exactly when the count is 1;
and a complete run with zero findings gives exactly "All three ledgers agree. Nothing to report tonight."

### P12: keys, not rows (validates Req 2.4, 2.5)

For any run, `ledger_key_counts(run)[ledger]` equals the number of distinct non-null keys in that ledger's in-scope
records, adding unkeyed rows or duplicate rows of an existing key does not change it, and a missing ledger gives `None`.

### P13: money is shown exactly (validates Req 3.1–3.3)

For any decimal amount (the `amounts()` strategy: many decimals, exponent form, zero, negative zero, negative),
`money_text` parses back to the same value (after removing `$`, commas and mapping U+2212 to `-`), never shows fewer than
two fraction digits, and shows a minus sign only for a value below zero. For any run, `keyed_total + unkeyed_total ==
billed_total` exactly. The TypeScript `moneyText` matches `money_text` on the generated fixture.

### P14: the report escapes ledger values (validates Req 7.3, 11.1)

For any ledger text (hostile unicode plus HTML and script payloads) placed in keys, attributes and context, the parsed
`report_html` contains only the tags `report.py` writes, no attribute that starts with `on`, no `<script>`, and the text
appears in the parsed text content unchanged.

### P15: browser and Python agree on every pack (validates Req 6.1, 6.4)

For any generated evidence pack whose records carry hostile unicode (bidi overrides, astral characters, quotes,
backslashes, control characters, lone surrogates in attribute values) and for either no change or one changed character
at any position of any row, the shipped `assets/verify.js` running in headless Chromium returns the same `ok` and the same
`failedRow` as `verify_evidence_pack`, and on success the same final hash. One browser page is reused across examples.
