// What is compared: each ledger's label, where its rows come from and how many keys it holds, beside the Venn diagram,
// with the region legend as the keyboard path to the same filter (ui-kit Req 2.3-2.6).

import { esc } from "../format";
import { GLYPHS } from "../glyphs";
import type { RunResult } from "../types";
import { LEDGERS, REGION_ORDER } from "../types";
import { vennSvg } from "./venn";

function counts(run: RunResult): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [code, summary] of Object.entries(run.region_summaries)) out[code] = summary.key_count;
  return out;
}

function ledgerList(run: RunResult): string {
  return LEDGERS.map((name, i) => {
    const words = run.ui.ledgers[name] ?? { label: name, source: "" };
    const keys = run.view.ledger_keys[name];
    const noun = keys === 1 ? "key" : "keys";
    const count =
      keys === null || keys === undefined
        ? run.missing_ledgers.includes(name)
          ? "not read"
          : "not matched"
        : `${keys} ${noun}`;
    return `<li class="ledger">
      <p class="ledger-head"><span class="ledger-letter" aria-hidden="true">${"IOB"[i]}</span><span class="ledger-label">${esc(words.label)}</span><span class="ledger-count">${esc(count)}</span></p>
      <p class="ledger-source">${esc(words.source)}</p>
    </li>`;
  }).join("");
}

function legend(run: RunResult, selected: string | null): string {
  const items = REGION_ORDER.map((code) => {
    const n = run.region_summaries[code]?.key_count ?? 0;
    const tone = code === "IOB" ? "living" : code === "IO" ? "familiar" : "finding";
    return `<li><button type="button" class="legend-item ${tone}${n ? " has" : ""}" data-region="${code}" aria-pressed="${selected === code}">
        <span class="legend-glyph">${GLYPHS[code] ?? ""}</span>
        <span class="legend-name">${esc(run.region_names[code] ?? code)}</span>
        <span class="legend-count">${n}</span>
        <span class="legend-code">${code}</span>
      </button></li>`;
  }).join("");
  return `<h2 class="rule-title" id="legend-title">Regions</h2><ul class="legend" aria-labelledby="legend-title">${items}</ul>`;
}

export function compare(run: RunResult, selected: string | null): string {
  const labels: Record<string, string> = {};
  for (const name of LEDGERS) labels[name] = run.ui.ledgers[name]?.label ?? name;
  const calm = run.view.calm;
  const venn = vennSvg({ counts: counts(run), names: run.region_names, ledgerLabels: labels, selected, calm });
  return `<section class="compare" aria-label="What is compared">
    <div class="venn-wrap">${venn}</div>
    <div class="compare-side">
      <h2 class="rule-title">Three ledgers</h2>
      <ol class="ledgers">${ledgerList(run)}</ol>
      ${calm ? "" : legend(run, selected)}
    </div>
  </section>`;
}
