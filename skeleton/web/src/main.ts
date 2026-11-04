import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "./style.css";

import { GLYPHS } from "./glyphs";
import { REGION_ORDER, type Finding, type RunResult, type RunSummary } from "./types";
import { regionAt, vennSvg } from "./venn";

// ---------------------------------------------------------------------------------------------------------------
// Data access. Live mode reads the API; demo mode (?demo=1) reads recorded runs shipped with the static build.

const params = new URLSearchParams(location.search);
const DEMO = params.get("demo") === "1" || document.querySelector('meta[name="nightaudit-demo"]') !== null;

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText} for ${url}`);
  return (await response.json()) as T;
}

const api = {
  runs: (): Promise<RunSummary[]> => getJson(DEMO ? "./demo/runs.json" : "/api/runs"),
  run: (id: string): Promise<RunResult> => getJson(DEMO ? `./demo/${id}.json` : `/api/runs/${id}`),
  evidenceUrl: (id: string): string => (DEMO ? `./demo/evidence-${id}.zip` : `/api/runs/${id}/evidence.zip`),
};

// ---------------------------------------------------------------------------------------------------------------
// Formatting. Every value from a ledger is untrusted text and goes through esc().

function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function money(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return esc(value);
  const abs = Math.abs(n);
  const digits = abs !== 0 && abs < 1 ? Math.min(4, Math.max(2, (value.split(".")[1] ?? "").length)) : 2;
  return `${n < 0 ? "−" : ""}$${abs.toFixed(digits)}`;
}

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function stamp(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} UTC · ${String(d.getUTCDate()).padStart(2, "0")} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${String(d.getUTCDate()).padStart(2, "0")} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

function haunting(f: Finding): string {
  if (f.status === "new" || !f.nights_persisted) return '<span class="tag new">NEW TONIGHT</span>';
  const n = f.nights_persisted;
  const cls = n > 3 ? "tag old" : "tag";
  return `<span class="${cls}">HAUNTING ${n} NIGHT${n === 1 ? "" : "S"}</span>`;
}

// ---------------------------------------------------------------------------------------------------------------
// State and rendering.

interface State {
  runs: RunSummary[];
  run: RunResult | null;
  region: string | null;
  open: Set<string>;
  error: string | null;
}

const state: State = { runs: [], run: null, region: params.get("region"), open: new Set(), error: null };
const root = document.getElementById("app") as HTMLElement;

function counts(run: RunResult): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [code, summary] of Object.entries(run.region_summaries)) out[code] = summary.key_count;
  return out;
}

function ledgerTotals(run: RunResult): Record<string, number> {
  const out: Record<string, number> = {};
  for (const s of run.snapshots) if (!s.missing) out[s.name] = s.records.length;
  return out;
}

function sum(record: Record<string, number> | undefined): number {
  return Object.values(record ?? {}).reduce((a, b) => a + b, 0);
}

function renderMasthead(run: RunResult): string {
  const options = state.runs
    .map(
      (r) =>
        `<option value="${esc(r.run_id)}" ${r.run_id === run.run_id ? "selected" : ""}>Night of ${esc(
          shortDate(r.run_time),
        )} · ${r.findings} findings</option>`,
    )
    .join("");
  return `<header class="masthead">
    <div class="brand"><span class="brand-mark" aria-hidden="true">◐</span> NIGHT AUDIT</div>
    <div class="masthead-meta">
      <span class="control">${esc(run.control_title || run.control_id)}</span>
      <label class="run-pick"><span class="sr-only">Run</span>
        <select id="run-select">${options}</select></label>
    </div>
    <div class="scanline" aria-hidden="true"></div>
  </header>`;
}

function renderIncomplete(run: RunResult): string {
  if (run.complete) return "";
  const lines = run.missing_ledgers
    .map((l) => `<li><strong>${esc(l.toUpperCase())}</strong> ledger missing: ${esc(run.ledger_errors[l] ?? "")}</li>`)
    .join("");
  return `<section class="incomplete" role="alert">
    <h2>INCOMPLETE RUN</h2>
    <p>A ledger could not be read, so this night produces no findings. Nothing below depends on the missing ledger.</p>
    <ul>${lines}</ul>
  </section>`;
}

function renderTally(run: RunResult): string {
  const findings = run.findings.filter((f) => !f.informational);
  const fresh = findings.filter((f) => f.status === "new").length;
  const old = findings.length - fresh;
  const legend = REGION_ORDER.map((code) => {
    const n = run.region_summaries[code]?.key_count ?? 0;
    const name = run.region_names[code] ?? code;
    const pressed = state.region === code;
    return `<li><button type="button" class="legend-item${n ? " has" : ""}" data-region="${code}" aria-pressed="${pressed}">
        <span class="legend-glyph">${GLYPHS[code] ?? ""}</span>
        <span class="legend-name">${esc(name)}</span>
        <span class="legend-count">${n}</span>
        <span class="legend-code">${code}</span>
      </button></li>`;
  }).join("");
  return `<div class="tally">
    <dl class="printout">
      <div><dt>TONIGHT</dt><dd><span class="hot">${fresh} new</span> · ${old} haunting</dd></div>
      <div><dt>ON THE BILL</dt><dd>${money(run.billed_total)} <span class="dim">(no resource id ${money(run.billed_unkeyed)})</span></dd></div>
      <div><dt>PENDING</dt><dd>${run.pending_keys.length} <span class="dim">inside the grace window</span></dd></div>
      <div><dt>OUT OF SCOPE</dt><dd>${sum(run.excluded) + sum(run.dropped)} <span class="dim">records excluded by the owner</span></dd></div>
    </dl>
    <h2 class="legend-title" id="legend-title">Regions</h2>
    <ul class="legend" aria-labelledby="legend-title">${legend}</ul>
  </div>`;
}

function renderEvidence(f: Finding): string {
  const rows = f.records
    .map((r) => {
      const attrs = Object.entries(r.attrs)
        .map(([k, v]) => `<span class="attr"><span class="k">${esc(k)}</span>=<span class="v">${esc(v)}</span></span>`)
        .join(" ");
      return `<tr><td>${esc(r.ledger)}</td><td class="mono">${esc(r.row_id)}</td><td class="mono">${esc(r.raw_key)}</td>
        <td class="num">${r.amount === null ? "" : money(r.amount)}</td><td>${esc(shortDate(r.timestamp))}</td><td>${attrs}</td></tr>`;
    })
    .join("");
  const context = Object.entries(f.context)
    .map(([k, v]) => `<div><dt>${esc(k.replace(/_/g, " "))}</dt><dd class="mono">${esc(v)}</dd></div>`)
    .join("");
  return `<div class="evidence">
    ${context ? `<dl class="context">${context}</dl>` : ""}
    <table><caption class="sr-only">Evidence rows for ${esc(f.key)}</caption>
      <thead><tr><th scope="col">Ledger</th><th scope="col">Row</th><th scope="col">Raw key</th><th scope="col">Amount</th><th scope="col">Date</th><th scope="col">Attributes</th></tr></thead>
      <tbody>${rows}</tbody></table>
  </div>`;
}

const RANK: Record<string, number> = Object.fromEntries(REGION_ORDER.map((code, i) => [code, i]));

function byPriority(a: Finding, b: Finding): number {
  const fresh = (f: Finding): number => (f.status === "new" ? 0 : 1);
  return (
    fresh(a) - fresh(b) ||
    (RANK[a.region_code] ?? 99) - (RANK[b.region_code] ?? 99) ||
    Number(b.billed_amount) - Number(a.billed_amount) ||
    a.key.localeCompare(b.key)
  );
}

function renderFindings(run: RunResult): string {
  const visible = run.findings
    .filter((f) => (state.region ? f.region_code === state.region : !f.informational))
    .sort(byPriority);
  const label = state.region ? run.region_names[state.region] ?? state.region : "All findings";
  const items = visible
    .map((f, i) => {
      const id = `f-${i}`;
      const open = state.open.has(f.key);
      return `<li class="row">
        <button type="button" class="row-head" aria-expanded="${open}" aria-controls="${id}" data-key="${esc(f.key)}">
          <span class="row-name">${GLYPHS[f.region_code] ?? ""}<span>${esc(f.name)}</span></span>
          <span class="row-key mono">${esc(f.key)}</span>
          <span class="row-status">${haunting(f)}</span>
          <span class="row-amount num">${money(f.billed_amount)}</span>
        </button>
        <p class="row-explain">${esc(f.explanation ?? f.meaning)}</p>
        <div id="${id}" class="row-body" ${open ? "" : "hidden"}>${open ? renderEvidence(f) : ""}</div>
      </li>`;
    })
    .join("");
  const matched = Object.entries(run.regions)
    .filter(([, code]) => code === "IOB")
    .map(([key]) => key)
    .sort();
  const empty =
    state.region === "IOB" && matched.length
      ? `<p class="empty">${matched.length} keys appear in all three ledgers. Matched keys are not findings.</p>
         <ul class="matched">${matched.map((k) => `<li class="mono">${esc(k)}</li>`).join("")}</ul>`
      : run.complete
        ? `<p class="empty">Nothing in this region tonight.</p>`
        : `<p class="empty">No findings: the run is incomplete.</p>`;
  return `<section id="findings" class="findings" aria-labelledby="findings-title" tabindex="-1">
    <div class="findings-head">
      <h2 id="findings-title">${esc(label)} <span class="dim">· ${visible.length}</span></h2>
      ${state.region ? '<button type="button" class="clear" id="clear-filter">Show all findings</button>' : ""}
    </div>
    ${visible.length ? `<ol class="rows">${items}</ol>` : empty}
  </section>`;
}

function renderFooter(run: RunResult): string {
  return `<footer class="foot">
    <dl class="printout small">
      <div><dt>EVIDENCE CHAIN</dt><dd class="mono">${esc(run.evidence_chain_hash ?? "—")}</dd></div>
      <div><dt>CONTROL</dt><dd class="mono">${esc(run.control_id)} · ${esc(run.control_hash.slice(0, 16))}</dd></div>
      <div><dt>RUN</dt><dd class="mono">${esc(run.run_id)}</dd></div>
    </dl>
    <p><a class="download" href="${api.evidenceUrl(run.run_id)}" download>Download the evidence pack</a>
      <span class="dim">then check it with <code>nightaudit verify &lt;pack&gt;</code></span></p>
  </footer>`;
}

function render(): void {
  if (state.error) {
    root.innerHTML = `<main class="page"><section class="incomplete" role="alert"><h2>CANNOT LOAD</h2><p>${esc(state.error)}</p></section></main>`;
    return;
  }
  const run = state.run;
  if (!run) {
    root.innerHTML = `<main class="page"><p class="loading">Reading the ledgers…</p></main>`;
    return;
  }
  root.innerHTML = `${renderMasthead(run)}
    <main class="page">
      <p class="when">${esc(stamp(run.run_time))}</p>
      ${renderIncomplete(run)}
      <section class="summary" aria-label="Summary">
        <div class="venn-wrap">${vennSvg({ counts: counts(run), names: run.region_names, selected: state.region, ledgerTotals: ledgerTotals(run) })}</div>
        ${renderTally(run)}
      </section>
      ${renderFindings(run)}
      ${renderFooter(run)}
    </main>`;
  bind(run);
}

function setRegion(code: string | null): void {
  state.region = state.region === code ? null : code;
  const url = new URL(location.href);
  if (state.region) url.searchParams.set("region", state.region);
  else url.searchParams.delete("region");
  history.replaceState(null, "", url);
  render();
}

function bind(run: RunResult): void {
  root.querySelector<HTMLSelectElement>("#run-select")?.addEventListener("change", (e) => {
    void load((e.target as HTMLSelectElement).value);
  });
  root.querySelectorAll<HTMLButtonElement>(".legend-item").forEach((b) =>
    b.addEventListener("click", () => {
      setRegion(b.dataset.region ?? null);
      root.querySelector<HTMLButtonElement>(`.legend-item[data-region="${b.dataset.region}"]`)?.focus();
    }),
  );
  root.querySelector<HTMLButtonElement>("#clear-filter")?.addEventListener("click", () => setRegion(state.region));
  const svg = root.querySelector<SVGSVGElement>("svg.venn");
  svg?.addEventListener("click", (e) => {
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    const code = regionAt(p.x, p.y);
    if (code) setRegion(code);
  });
  root.querySelectorAll<HTMLButtonElement>(".row-head").forEach((b) =>
    b.addEventListener("click", () => {
      const key = b.dataset.key ?? "";
      if (state.open.has(key)) state.open.delete(key);
      else state.open.add(key);
      render();
      root.querySelector<HTMLButtonElement>(`.row-head[data-key="${CSS.escape(key)}"]`)?.focus();
    }),
  );
  void run;
}

async function load(runId?: string): Promise<void> {
  try {
    if (!state.runs.length) state.runs = await api.runs();
    const id = runId ?? params.get("run") ?? state.runs[0]?.run_id;
    if (!id) {
      state.error = "No runs yet. Run a control with: nightaudit run <control.yaml>";
      render();
      return;
    }
    state.run = await api.run(id);
    state.open.clear();
    state.error = null;
  } catch (err) {
    state.error = err instanceof Error ? err.message : String(err);
  }
  render();
}

render();
void load();
