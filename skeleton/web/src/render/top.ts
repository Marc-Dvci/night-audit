// Masthead and lede: what this is, which night, and tonight's result in one sentence (ui-kit Req 2.1, 3, 7.2, 8).

import type { Source } from "../api";
import { dateText, esc, stampText } from "../format";
import type { AppEntry, RunResult, RunSummary } from "../types";

export function masthead(run: RunResult, apps: AppEntry[], app: AppEntry, runs: RunSummary[], src: Source, sweep: boolean): string {
  const appSwitch =
    apps.length > 1
      ? `<label class="mast-field"><span class="mast-label">App</span>
          <select id="app-select">${apps
            .map((a) => `<option value="${esc(a.name)}"${a.name === app.name ? " selected" : ""}>${esc(a.title)}${a.mode === "demo" ? " (recorded)" : ""}</option>`)
            .join("")}</select></label>`
      : `<span class="mast-app">${esc(app.title)}</span>`;
  const nights = runs.filter((r) => r.control_id === run.control_id);
  const options = nights
    .map((r) => `<option value="${esc(r.run_id)}"${r.run_id === run.run_id ? " selected" : ""}>${esc(dateText(r.run_time))} · ${r.findings} ${r.findings === 1 ? "finding" : "findings"}</option>`)
    .join("");
  const recorded =
    app.mode === "demo" ? `<p class="recorded">Recorded run of a synthetic account. Not live data.</p>` : "";
  return `<header class="masthead${sweep ? " sweep" : ""}">
    <div class="mast-line">
      <p class="brand"><span class="brand-mark" aria-hidden="true">◐</span>NIGHT AUDIT</p>
      <div class="mast-meta">
        ${appSwitch}
        <label class="mast-field"><span class="mast-label">Night</span><select id="run-select">${options}</select></label>
        <a class="mast-link" href="${esc(src.report(run.run_id))}">Morning report</a>
      </div>
    </div>
    ${recorded}
    <div class="scanline" aria-hidden="true"></div>
  </header>`;
}

export function lede(run: RunResult): string {
  const view = run.view;
  const lines = view.lines
    .map(
      (line) => `<div class="money-line">
        <dt>${esc(line.label)}</dt>
        <dd class="money-value">${esc(line.value)}</dd>
        ${line.note ? `<dd class="money-note">${esc(line.note)}</dd>` : ""}
      </div>`,
    )
    .join("");
  const missing = run.complete
    ? ""
    : `<div class="incomplete" role="alert"><p class="incomplete-title">INCOMPLETE NIGHT</p><ul>${run.missing_ledgers
        .map((l) => `<li><span class="mono">${esc(run.ui.ledgers[l]?.label ?? l)}</span>: ${esc(run.ledger_errors[l] ?? "not read")}</li>`)
        .join("")}</ul><p>No finding can be confirmed without every ledger, so nothing below depends on the missing one.</p></div>`;
  const pending = view.pending_count
    ? `<p class="pending">${view.pending_count} ${view.pending_count === 1 ? run.ui.noun.singular : run.ui.noun.plural} pending: seen, but billing data has not arrived yet.</p>`
    : "";
  return `<section class="lede${view.calm ? " calm" : ""}" aria-labelledby="headline">
    <p class="tagline">${esc(run.ui.tagline)}</p>
    <h1 id="headline" class="headline">${esc(view.headline)}</h1>
    <p class="stamp">${esc(run.control_title || run.ui.title)} · night of ${esc(stampText(run.run_time))}</p>
    ${missing}
    ${lines ? `<dl class="money">${lines}</dl>` : ""}
    ${pending}
  </section>`;
}
