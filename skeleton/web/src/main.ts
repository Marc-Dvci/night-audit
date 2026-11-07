import "./fonts.css";
import "./style.css";

import { getText, loadApps, source, type Source } from "./api";
import { dateText, esc } from "./format";
import { compare } from "./render/compare";
import { footer } from "./render/footer";
import { nights } from "./render/nights";
import { findings, laidToRest } from "./render/rows";
import { lede, masthead } from "./render/top";
import { regionAt } from "./render/venn";
import { emptyVerify, pickApp, readUrl, sanitise, writeUrl, type State } from "./state";
import type { AppEntry, RunSummary } from "./types";

const root = document.getElementById("app") as HTMLElement;
const reducedMotion = (): boolean => matchMedia("(prefers-reduced-motion: reduce)").matches;
const nextFrame = (): Promise<void> => new Promise((resolve) => requestAnimationFrame(() => resolve()));

const state: State = {
  apps: [],
  app: null,
  runs: [],
  run: null,
  region: null,
  open: null,
  error: null,
  verify: emptyVerify(),
  focus: null,
  sweep: false,
};
let src: Source | null = null;
let evidenceCache: { runId: string; jsonl: string; manifest: Record<string, unknown> } | null = null;

// ---------------------------------------------------------------------------------------------------------------------
// Rendering. The whole page is rebuilt from state; every ledger value passes through esc() in the render modules.

function render(): void {
  const run = state.run;
  if (state.error) {
    root.innerHTML = `<main class="page"><section class="incomplete" role="alert"><p class="incomplete-title">CANNOT LOAD</p><p>${esc(state.error)}</p></section></main>`;
    return;
  }
  if (!run || !state.app || !src) {
    root.innerHTML = `<main class="page"><p class="loading">Reading the ledgers…</p></main>`;
    return;
  }
  root.innerHTML = `${masthead(run, state.apps, state.app, state.runs, src, state.sweep)}
    <main class="page" id="main">
      ${lede(run, src)}
      ${compare(run, state.region)}
      ${nights(run, state.runs)}
      ${findings(run, state.region, state.open)}
      ${laidToRest(run)}
      ${footer(run, src, state.verify)}
    </main>`;
  state.sweep = false;
  document.title = `Night Audit · ${run.ui.title} · ${dateText(run.run_time)}`;
  writeUrl(state);
  if (state.focus) {
    root.querySelector<HTMLElement>(state.focus)?.focus();
    state.focus = null;
  }
}

function rowSelector(key: string): string {
  return `.row-head[data-key="${CSS.escape(key)}"]`;
}

// ---------------------------------------------------------------------------------------------------------------------
// Loading.

async function liveOrDemo(apps: AppEntry[], wanted: string | null): Promise<{ app: AppEntry; runs: RunSummary[] }> {
  const first = pickApp(apps, wanted);
  if (!first) throw new Error("No apps are configured.");
  const order = [first, ...apps.filter((a) => a !== first)];
  let lastError: unknown = null;
  for (const app of order) {
    try {
      const runs = await source(app).runs();
      if (runs.length || app === order[order.length - 1]) return { app, runs };
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError instanceof Error ? lastError : new Error("No runs yet. Run a control with: nightaudit run <control.yaml>");
}

async function loadRun(runId: string, region: string | null, open: string | null): Promise<void> {
  if (!src) return;
  try {
    const run = await src.run(runId);
    const clean = sanitise(run, region, open);
    state.run = run;
    state.region = clean.region;
    state.open = clean.open;
    state.verify = emptyVerify();
    state.error = null;
    state.sweep = true;
  } catch (err) {
    state.error = err instanceof Error ? err.message : String(err);
  }
  render();
}

async function boot(): Promise<void> {
  const wanted = readUrl(location.href);
  const fonts = Promise.all(
    ["400 1em 'IBM Plex Sans'", "600 1em 'IBM Plex Sans'", "400 1em 'IBM Plex Mono'", "600 1em 'IBM Plex Mono'"].map((f) =>
      document.fonts.load(f).catch(() => []),
    ),
  );
  try {
    state.apps = await loadApps();
    const { app, runs } = await liveOrDemo(state.apps, wanted.app);
    state.app = app;
    state.runs = runs;
    src = source(app);
    if (!runs.length) throw new Error("No runs yet. Run a control with: nightaudit run <control.yaml>");
    const runId = runs.some((r) => r.run_id === wanted.run) ? (wanted.run as string) : runs[0].run_id;
    // Text is drawn once, in its final font, so nothing moves when the fonts arrive (ui-kit Req 9.2).
    await fonts;
    await loadRun(runId, wanted.region, wanted.open);
  } catch (err) {
    await fonts;
    state.error = err instanceof Error ? err.message : String(err);
    render();
    return;
  }
  if (state.open) {
    // Landing on a deep link jumps straight to the finding; there is nothing to animate from.
    const head = root.querySelector<HTMLElement>(rowSelector(state.open));
    head?.closest(".row")?.scrollIntoView({ block: "start", behavior: "instant" });
    head?.focus({ preventScroll: true });
  }
}

// ---------------------------------------------------------------------------------------------------------------------
// Verify this night: recompute the chain in the browser and print it like a line printer.

function printerLine(index: number, type: string, ledger: string, rowId: string, hash: string): string {
  const id = rowId.length > 30 ? `${rowId.slice(0, 29)}…` : rowId;
  return `ROW ${String(index).padStart(3, "0")}  ${type.padEnd(7)} ${ledger.padEnd(9)} ${id.padEnd(30)} ${hash.slice(0, 12)}  OK`;
}

async function verify(change: "none" | "tamper" = "none"): Promise<void> {
  const run = state.run;
  if (!run || !src) return;
  const { changeOneByte, verifyPack } = await import("./verify");
  state.verify = { ...emptyVerify(), busy: true, tampered: change === "tamper", verdict: "Downloading evidence.jsonl and manifest.json…" };
  state.focus = `[data-action="verify"]`;
  render();
  try {
    if (!evidenceCache || evidenceCache.runId !== run.run_id) {
      const [jsonl, manifest] = await Promise.all([getText(src.evidence(run.run_id)), getText(src.manifest(run.run_id))]);
      evidenceCache = { runId: run.run_id, jsonl, manifest: JSON.parse(manifest) as Record<string, unknown> };
    }
    let text = evidenceCache.jsonl;
    let note = "";
    if (change === "tamper") {
      const changed = changeOneByte(text);
      if (!changed) throw new Error("This pack has no record row to change.");
      text = changed.text;
      note = ` In memory only, row ${String(changed.row).padStart(3, "0")} had "${changed.before}" changed to "${changed.after}".`;
    }
    const lines: string[] = [`VERIFY ${dateText(run.run_time).toUpperCase()}  evidence.jsonl, manifest.json`];
    const printer = root.querySelector<HTMLElement>("#printer");
    const animate = !reducedMotion();
    if (printer) printer.textContent = animate ? lines[0] : "";
    const total = Math.max(1, text.split("\n").length - 1);
    const perFrame = Math.max(1, Math.ceil(total / 60));
    const result = await verifyPack(
      text,
      evidenceCache.manifest,
      animate
        ? async (row) => {
            lines.push(printerLine(row.index, row.type, row.ledger, row.rowId, row.hash));
            if (row.index % perFrame === perFrame - 1) {
              if (printer) printer.textContent = lines.join("\n");
              await nextFrame();
            }
          }
        : undefined,
      // What the page displays must also be what the chain holds: a fake finding fails here (Req 6.6).
      run as unknown as Record<string, unknown>,
    );
    const pageHash = run.evidence_chain_hash;
    let verdict: string;
    let ok = result.ok;
    if (result.ok && result.finalHash === evidenceCache.manifest.final_chain_hash && result.finalHash === pageHash) {
      verdict = `VERIFIED  ${result.rows} rows, ${result.findings} findings. Final hash ${result.finalHash} matches the manifest and the hash on this page. The findings and figures on this page match the chain.${
        result.hasHeader ? "" : " This older pack has no header row, so its run id and run time are not bound to the chain."
      }`;
    } else if (result.ok) {
      ok = false;
      verdict = `CHAIN IS WHOLE, BUT  its final hash ${result.finalHash} differs from the hash on this page.`;
    } else {
      const where = result.failedRow === null ? "" : ` at row ${String(result.failedRow).padStart(3, "0")}`;
      const why = result.detail.replace(/^row \d+: /, "");
      verdict = `FAILED${where}  ${why}.${note}`;
    }
    state.verify = { lines: animate ? lines : [], verdict, ok, busy: false, tampered: change === "tamper" };
  } catch (err) {
    state.verify = { ...emptyVerify(), verdict: `CANNOT VERIFY  ${err instanceof Error ? err.message : String(err)}`, ok: false };
  }
  state.focus = change === "tamper" ? `[data-action="restore"]` : `[data-action="verify"]`;
  render();
}

// ---------------------------------------------------------------------------------------------------------------------
// Events, delegated from the root so a re-render needs no re-binding.

function setRegion(code: string | null, focus: string | null): void {
  state.region = state.region === code ? null : code;
  state.open = null;
  state.focus = focus;
  render();
}

root.addEventListener("click", (event) => {
  const target = event.target as Element;
  const region = target.closest<HTMLElement>("[data-region]");
  if (region) return setRegion(region.dataset.region ?? null, `.legend-item[data-region="${region.dataset.region}"]`);
  const action = target.closest<HTMLElement>("[data-action]")?.dataset.action;
  if (action === "clear-filter") return setRegion(state.region, `.legend-item[data-region="${state.region}"]`);
  if (action === "verify") return void verify();
  if (action === "tamper") return void verify("tamper");
  if (action === "restore") return void verify();
  const night = target.closest<HTMLElement>("[data-run]");
  if (night?.dataset.run) {
    state.focus = `.night[data-run="${CSS.escape(night.dataset.run)}"]`;
    return void loadRun(night.dataset.run, state.region, null);
  }
  const head = target.closest<HTMLElement>(".row-head");
  if (head) {
    const key = head.dataset.key ?? "";
    state.open = state.open === key ? null : key;
    state.focus = rowSelector(key);
    return render();
  }
  const svg = target.closest<SVGSVGElement>("svg.venn");
  if (svg && event instanceof MouseEvent) {
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(ctm.inverse());
    const code = regionAt(p.x, p.y);
    if (code) setRegion(code, null);
  }
});

root.addEventListener("change", (event) => {
  const target = event.target as HTMLSelectElement;
  if (target.id === "run-select") {
    state.focus = "#run-select";
    void loadRun(target.value, state.region, null);
  } else if (target.id === "app-select") {
    const url = new URL(location.href);
    url.search = "";
    url.searchParams.set("app", target.value);
    location.assign(url.href);
  }
});

render();
void boot();
