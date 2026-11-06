// The nights strip: up to 30 recent nights of this control, oldest to newest. Each mark is a button whose height
// follows its finding count, with the count and the new count written as text too (ui-kit Req 4.1).

import { dateText, dayText, esc } from "../format";
import type { RunResult, RunSummary } from "../types";

export const MAX_NIGHTS = 30;

export function nights(run: RunResult, runs: RunSummary[]): string {
  const strip = runs
    .filter((r) => r.control_id === run.control_id)
    .slice(0, MAX_NIGHTS)
    .reverse();
  if (!strip.length) return "";
  const most = Math.max(1, ...strip.map((r) => r.findings));
  const marks = strip
    .map((r) => {
      const height = r.findings === 0 ? 0 : Math.max(1, Math.round((r.findings / most) * 10));
      const fresh = r.new_findings ?? 0;
      const current = r.run_id === run.run_id;
      const state = !r.complete ? " incomplete" : r.findings === 0 ? " clean" : "";
      return `<li><button type="button" class="night h-${height}${fresh ? " fresh" : ""}${state}" data-run="${esc(r.run_id)}"${
        current ? ' aria-current="date"' : ""
      }>
        <span class="night-bar" aria-hidden="true"></span>
        <span class="night-day"><span class="sr-only">Night of ${esc(dateText(r.run_time))}, </span><span aria-hidden="true">${esc(dayText(r.run_time))}</span></span>
        <span class="night-count">${r.complete ? `${r.findings}<span class="sr-only"> ${r.findings === 1 ? "finding" : "findings"}</span>${fresh ? ` · <span class="night-new">${fresh} new</span>` : ""}` : "incomplete"}</span>
      </button></li>`;
    })
    .join("");
  return `<section class="nights" aria-labelledby="nights-title">
    <h2 class="rule-title" id="nights-title">Nights</h2>
    <ol class="strip">${marks}</ol>
  </section>`;
}
