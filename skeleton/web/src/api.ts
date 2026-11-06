// Data access. A live app reads the API; a demo app reads recorded runs shipped with the static build. Both expose the
// same files per run: the run document, evidence.jsonl, manifest.json, report.html and the evidence zip.

import type { AppEntry, RunResult, RunSummary } from "./types";

const FALLBACK_APPS: AppEntry[] = [{ name: "live", title: "Night Audit", mode: "live", base: "api/" }];

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText} for ${url}`);
  return (await response.json()) as T;
}

export async function getText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText} for ${url}`);
  return response.text();
}

export async function loadApps(): Promise<AppEntry[]> {
  try {
    const apps = await getJson<AppEntry[]>("./apps.json");
    return Array.isArray(apps) && apps.length ? apps : FALLBACK_APPS;
  } catch {
    return FALLBACK_APPS;
  }
}

export interface Source {
  runs(): Promise<RunSummary[]>;
  run(id: string): Promise<RunResult>;
  evidence(id: string): string;
  manifest(id: string): string;
  report(id: string): string;
  zip(id: string): string;
}

const enc = encodeURIComponent;

export function source(app: AppEntry): Source {
  const base = app.base.endsWith("/") ? app.base : `${app.base}/`;
  if (app.mode === "demo") {
    return {
      runs: () => getJson(`${base}runs.json`),
      run: (id) => getJson(`${base}${enc(id)}/run.json`),
      evidence: (id) => `${base}${enc(id)}/evidence.jsonl`,
      manifest: (id) => `${base}${enc(id)}/manifest.json`,
      report: (id) => `${base}${enc(id)}/report.html`,
      zip: (id) => `${base}${enc(id)}/evidence.zip`,
    };
  }
  return {
    runs: () => getJson(`${base}runs`),
    run: (id) => getJson(`${base}runs/${enc(id)}`),
    evidence: (id) => `${base}runs/${enc(id)}/evidence.jsonl`,
    manifest: (id) => `${base}runs/${enc(id)}/manifest.json`,
    report: (id) => `${base}runs/${enc(id)}/report.html`,
    zip: (id) => `${base}runs/${enc(id)}/evidence.zip`,
  };
}
