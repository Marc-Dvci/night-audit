// The page state and its URL. ?app=, ?run=, ?region= and ?open= are read on load and written back on every change, so
// a link always reopens what the reader sees (ui-kit Req 5.1). Values that name nothing in the run are dropped (Req 5.2).

import type { AppEntry, RunResult, RunSummary } from "./types";
import { REGION_CODES } from "./types";

export interface VerifyState {
  lines: string[];
  verdict: string;
  ok: boolean | null;
  busy: boolean;
  tampered: boolean;
}

export interface State {
  apps: AppEntry[];
  app: AppEntry | null;
  runs: RunSummary[];
  run: RunResult | null;
  region: string | null;
  open: string | null;
  error: string | null;
  verify: VerifyState;
  /** Selector of the element to focus after the next render. */
  focus: string | null;
  /** Sweep the scan line on the next render: a run has just been loaded. */
  sweep: boolean;
}

export interface Wanted {
  app: string | null;
  run: string | null;
  region: string | null;
  open: string | null;
}

export function emptyVerify(): VerifyState {
  return { lines: [], verdict: "", ok: null, busy: false, tampered: false };
}

export function readUrl(href: string): Wanted {
  const params = new URL(href).searchParams;
  return {
    app: params.get("app") ?? (params.get("demo") === "1" ? "demo" : null),
    run: params.get("run"),
    region: params.get("region"),
    open: params.get("open"),
  };
}

/** The app the URL names, or the first app, or (for the old ?demo=1 link) the first demo app. */
export function pickApp(apps: AppEntry[], wanted: string | null): AppEntry | null {
  if (wanted === "demo") return apps.find((a) => a.mode === "demo") ?? apps[0] ?? null;
  return apps.find((a) => a.name === wanted) ?? apps[0] ?? null;
}

/** Keep a region filter only when it is one of the seven codes; keep an open key only when it is a finding. */
export function sanitise(run: RunResult, region: string | null, open: string | null): { region: string | null; open: string | null } {
  const okRegion = region !== null && REGION_CODES.has(region) ? region : null;
  const okOpen = open !== null && run.findings.some((f) => f.key === open) ? open : null;
  return { region: okRegion, open: okOpen };
}

export function writeUrl(state: State): void {
  const url = new URL(location.href);
  url.searchParams.delete("demo");
  const set = (name: string, value: string | null | undefined): void => {
    if (value) url.searchParams.set(name, value);
    else url.searchParams.delete(name);
  };
  set("app", state.app?.name);
  set("run", state.run?.run_id);
  set("region", state.region);
  set("open", state.open);
  if (url.href !== location.href) history.replaceState(null, "", url);
}
