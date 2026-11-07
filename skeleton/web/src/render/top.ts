// Masthead and lede: what this is, which night, and tonight's result in one sentence (ui-kit Req 2.1, 3, 7.2, 8), with
// the run's notes under it (Req 10.2) and the downloads and review decisions beside it (Req 10.6, 10.7).

import type { Source } from "../api";
import { dateText, esc, stampText } from "../format";
import type { AppEntry, RunResult, RunSummary } from "../types";

/** The sentences the control's summarisers added. Every number in them was checked against the evidence. */
function notes(run: RunResult): string {
  const items = (run.notes ?? []).map((n) => `<li>${esc(n.text)}</li>`).join("");
  return items ? `<ul class="notes" aria-label="Notes on tonight">${items}</ul>` : "";
}

export function masthead(run: RunResult, apps: AppEntry[], app: AppEntry, runs: RunSummary[], src: Source, sweep: boolean): string {
  const appSwitch =
    apps.length > 1
      ? `<label class="mast-field"><span class="mast-label">App</span>
          <select id="app-select">${apps
            .map((a) => `<option value="${esc(a.name)}"${a.name === app.name ? " selected" : ""}>${esc(a.title)}</option>`)
            .join("")}</select></label>`
      : `<span class="mast-app">${esc(app.title)}</span>`;
  const nights = runs.filter((r) => r.control_id === run.control_id);
  const options = nights
    .map((r) => `<option value="${esc(r.run_id)}"${r.run_id === run.run_id ? " selected" : ""}>${esc(dateText(r.run_time))} · ${r.findings} ${r.findings === 1 ? "finding" : "findings"}</option>`)
    .join("");
  const recorded =
    app.mode === "demo" ? `<p class="recorded">Recorded run. Not live data.</p>` : "";
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

/** The control's downloads and, when recorded, the review decisions: who decided how many, and on which dates. */
function review(run: RunResult, src: Source): string {
  const downloads = (run.downloads ?? [])
    .map((d) => `<li><a class="text-button" href="${esc(src.file(run.run_id, d.file))}" download="${esc(d.file)}">${esc(d.label)}</a></li>`)
    .join("");
  const decisions = run.decisions;
  let decided = "";
  if (decisions && !decisions.ok) {
    decided = `<p class="review-state failed">Decisions are recorded for this night, but they do not verify, so none is shown: ${esc(decisions.detail)}</p>`;
  } else if (decisions && decisions.rows.length) {
    const reviewers = [...new Set(decisions.rows.map((d) => d.reviewer))].sort();
    const dates = [...new Set(decisions.rows.map((d) => d.decision_date))].sort();
    const n = decisions.rows.length;
    decided = `<p class="review-state">${n} ${n === 1 ? "decision" : "decisions"} recorded by ${esc(reviewers.join(", "))} on ${esc(dates.join(", "))}. The decision chain verifies against this night's evidence.</p>`;
  } else if (downloads) {
    decided = `<p class="review-state">No decision recorded for this night yet.</p>`;
  }
  if (!downloads && !decided) return "";
  return `<h2 class="rule-title" id="review-title">Review</h2>
    ${decided}
    ${downloads ? `<ul class="downloads" aria-labelledby="review-title">${downloads}</ul>` : ""}`;
}

export function lede(run: RunResult, src: Source): string {
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
  const sentences = view.headline_sentences?.length ? view.headline_sentences : [view.headline];
  const [lead, ...rest] = sentences;
  const more = rest.length
    ? `<span class="headline-more">${rest.map((s) => `<span class="headline-line">${esc(s)}</span>`).join(" ")}</span>`
    : "";
  return `<section class="lede${view.calm ? " calm" : ""}" aria-labelledby="headline">
    <div class="lede-text">
      <p class="tagline">${esc(run.ui.tagline)}</p>
      <h1 id="headline" class="headline"><span class="headline-lead">${esc(lead)}</span>${rest.length ? " " : ""}${more}</h1>
      ${notes(run)}
      <p class="stamp">${esc(run.control_title || run.ui.title)} · night of ${esc(stampText(run.run_time))}</p>
      ${missing}
    </div>
    <div class="lede-side">
      ${lines ? `<h2 class="rule-title">The bill</h2><dl class="money">${lines}</dl>` : ""}
      ${pending}
      ${review(run, src)}
    </div>
  </section>`;
}
