// Finding rows: printout bands, one per finding, with the columns the control declares (ui-kit Req 4.2, 8.2), the
// filter note when a region is active (Req 2.6), the evidence table in its own scroll container (Req 10.3) and the
// findings laid to rest since the previous night (Req 4.3).

import { dateText, esc, moneyText, plural } from "../format";
import { GLYPHS } from "../glyphs";
import type { Finding, RunResult, UiColumn } from "../types";
import { LEDGERS, REGION_ORDER } from "../types";

const RANK: Record<string, number> = Object.fromEntries(REGION_ORDER.map((code, i) => [code, i]));

/** New first, then by region, then by key. Amounts are not compared: they are strings and stay strings. */
export function byPriority(a: Finding, b: Finding): number {
  const fresh = (f: Finding): number => (f.status === "new" ? 0 : 1);
  return fresh(a) - fresh(b) || (RANK[a.region_code] ?? 99) - (RANK[b.region_code] ?? 99) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);
}

/** Blood is only for a finding that has persisted more than 3 nights (ui-identity). */
export function tone(f: Finding): "new" | "old" | "haunting" {
  if (f.status === "new") return "new";
  return (f.nights_persisted ?? 0) > 3 ? "old" : "haunting";
}

function statusText(f: Finding): string {
  if (f.status === "new") return `<span class="nowrap">New tonight</span>`;
  const nights = f.nights_persisted ?? 0;
  return `<span class="nowrap">Since ${esc(dateText(f.first_seen))}</span> <span class="nowrap">· ${esc(plural(nights, "night", "nights"))}</span>`;
}

function attrOf(f: Finding, name: string): string {
  for (const ledger of LEDGERS) {
    const record = f.records.find((r) => r.ledger === ledger && r.attrs[name] !== undefined && r.attrs[name] !== "");
    if (record) return record.attrs[name];
  }
  return "";
}

/** The column kind sets its share of the row width (style.css: .c-key, .c-name, ...). */
function kind(column: UiColumn): string {
  return ["key", "name", "status", "amount"].includes(column.from) ? column.from : "attr";
}

function cell(f: Finding, column: UiColumn): string {
  const label = `<span class="cell-label">${esc(column.label)}</span>`;
  const source = column.from;
  let value: string;
  const cls = `cell c-${kind(column)}`;
  if (source === "key") {
    value = `<span class="mono key">${esc(f.key)}</span>`;
  } else if (source === "name") {
    value = `<span class="finding-name">${GLYPHS[f.region_code] ?? ""}<span>${esc(f.name)}</span></span>`;
  } else if (source === "status") {
    value = `<span class="status ${tone(f)}">${statusText(f)}</span>`;
  } else if (source === "amount") {
    value = f.region_code.includes("B") ? `<span class="mono nowrap">${esc(moneyText(f.billed_amount))}</span>` : `<span class="dim nowrap">not billed</span>`;
  } else {
    const [prefix, ...rest] = source.split(":");
    const name = rest.join(":");
    const text = prefix === "attr" ? attrOf(f, name) : (f.context[name] ?? "");
    value = text ? `<span class="mono">${esc(text)}</span>` : `<span class="dim">none</span>`;
  }
  return `<span class="${cls}">${label}<span class="cell-value">${value}</span></span>`;
}

function evidence(f: Finding, index: number): string {
  const rows = f.records
    .map((r) => {
      const attrs = Object.entries(r.attrs)
        .filter(([, v]) => v !== "")
        .map(([k, v]) => `<span class="attr"><span class="attr-k">${esc(k)}</span>=<span class="attr-v">${esc(v)}</span></span>`)
        .join(" ");
      return `<tr><td>${esc(r.ledger)}</td><td class="mono">${esc(r.row_id)}</td><td class="mono">${esc(r.raw_key)}</td>
        <td class="mono num">${r.amount === null ? "" : esc(moneyText(r.amount))}</td><td class="mono">${esc(dateText(r.timestamp))}</td><td>${attrs}</td></tr>`;
    })
    .join("");
  const context = Object.entries(f.context)
    .map(([k, v]) => `<div><dt>${esc(k.replace(/_/g, " "))}</dt><dd class="mono">${esc(v)}</dd></div>`)
    .join("");
  return `${context ? `<dl class="context">${context}</dl>` : ""}
    <div class="scroll" role="region" tabindex="0" aria-labelledby="ev-cap-${index}">
      <table class="evidence"><caption id="ev-cap-${index}" class="sr-only">Evidence rows for ${esc(f.key)}</caption>
        <thead><tr><th scope="col">Ledger</th><th scope="col">Row</th><th scope="col">Raw key</th><th scope="col">Amount</th><th scope="col">Date</th><th scope="col">Attributes</th></tr></thead>
        <tbody>${rows}</tbody></table>
    </div>`;
}

function filterNote(run: RunResult, region: string): string {
  return `<div class="filter-note">
    <p class="filter-name"><span class="filter-glyph">${GLYPHS[region] ?? ""}</span><span>${esc(run.region_names[region] ?? region)}</span><span class="filter-code">${region}</span></p>
    <p class="filter-meaning">${esc(run.region_meanings?.[region] ?? "")}</p>
    <button type="button" class="text-button" data-action="clear-filter">Show all findings</button>
  </div>`;
}

function matched(run: RunResult): string {
  const keys = Object.entries(run.regions)
    .filter(([, code]) => code === "IOB")
    .map(([key]) => key)
    .sort();
  if (!keys.length) return "";
  const noun = keys.length === 1 ? run.ui.noun.singular : run.ui.noun.plural;
  return `<p class="calm-line">${keys.length} ${esc(noun)} ${keys.length === 1 ? "appears" : "appear"} in all three ledgers.</p>
    <ul class="matched">${keys.map((k) => `<li class="mono">${esc(k)}</li>`).join("")}</ul>`;
}

/** A verified review decision on this finding, in words (Req 10.7). The page only receives decisions that verify. */
function decisionLine(run: RunResult, f: Finding): string {
  const d = run.decisions?.ok ? run.decisions.rows.find((r) => r.key === f.key && r.region_code === f.region_code) : undefined;
  if (!d) return "";
  return `<p class="row-decision"><span class="decision-word">Decision: ${esc(d.decision)}</span> <span class="nowrap">by ${esc(d.reviewer)}</span> <span class="nowrap">on ${esc(d.decision_date)}</span></p>`;
}

/** The night shift's note on this finding, when one was accepted and its chain verifies. No note, no markup. */
export const NOTE_LABEL = "Investigator's note, checked against the evidence";

function noteLine(run: RunResult, f: Finding): string {
  const n = run.investigator_notes?.ok
    ? run.investigator_notes.rows.find((r) => r.key === f.key && r.region_code === f.region_code)
    : undefined;
  if (!n) return "";
  return `<p class="row-note"><span class="note-label">${NOTE_LABEL}</span> <span class="note-text">${esc(n.text)}</span></p>`;
}

export function findings(run: RunResult, region: string | null, open: string | null): string {
  const columns = run.ui.columns.length ? run.ui.columns : [{ label: "Key", from: "key" }];
  const hasName = columns.some((c) => c.from === "name");
  const visible = run.findings.filter((f) => (region ? f.region_code === region : !f.informational)).sort(byPriority);

  const header = `<div class="colhead" aria-hidden="true">${columns
    .map((c) => `<span class="c-${kind(c)}">${esc(c.label)}</span>`)
    .join("")}</div>`;

  const items = visible
    .map((f, i) => {
      const isOpen = open === f.key;
      const name = hasName ? "" : `<p class="row-region">${GLYPHS[f.region_code] ?? ""}<span>${esc(f.name)}</span></p>`;
      return `<li class="row ${tone(f)}" id="row-${i}">
        ${name}
        <button type="button" class="row-head" aria-expanded="${isOpen}" aria-controls="ev-${i}" data-key="${esc(f.key)}">${columns
          .map((c) => cell(f, c))
          .join("")}</button>
        <p class="row-explain">${esc(f.explanation ?? f.meaning)}</p>
        ${decisionLine(run, f)}
        ${noteLine(run, f)}
        <div id="ev-${i}" class="row-body"${isOpen ? "" : " hidden"}>${isOpen ? evidence(f, i) : ""}</div>
      </li>`;
    })
    .join("");

  const title = region ? (run.region_names[region] ?? region) : "Findings";
  let body: string;
  if (visible.length) body = `${header}<ol class="rows">${items}</ol>`;
  else if (region === "IOB" || (!region && run.view.calm)) body = matched(run) || `<p class="empty">Nothing in this region tonight.</p>`;
  else if (!run.complete) body = `<p class="empty">No findings: the night is incomplete.</p>`;
  else body = `<p class="empty">Nothing in this region tonight.</p>`;

  return `<section id="rows" class="findings" tabindex="-1" aria-labelledby="rows-title">
    <h2 class="rule-title" id="rows-title">${esc(title)} <span class="rule-count">${visible.length}</span></h2>
    ${region ? filterNote(run, region) : ""}
    ${body}
  </section>`;
}

export function laidToRest(run: RunResult): string {
  const resolved = run.resolved.filter((f) => !f.informational).sort(byPriority);
  if (!resolved.length) return "";
  const items = resolved
    .map(
      (f) => `<li class="rest-row">
        <span class="rest-name">${GLYPHS[f.region_code] ?? ""}<span>${esc(f.name)}</span></span>
        <span class="mono key">${esc(f.key)}</span>
        <span class="rest-seen"><span class="cell-label">First seen</span>${esc(dateText(f.first_seen))}</span>
        <span class="rest-lasted"><span class="cell-label">Lasted</span>${esc(plural(f.nights_persisted ?? 0, "night", "nights"))}</span>
      </li>`,
    )
    .join("");
  return `<section class="rest" aria-labelledby="rest-title">
    <h2 class="rule-title" id="rest-title">Laid to rest <span class="rule-count">${resolved.length}</span></h2>
    <p class="rest-intro">Present last night, gone tonight.</p>
    <ol class="rest-rows">${items}</ol>
  </section>`;
}
