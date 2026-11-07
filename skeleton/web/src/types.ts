// Shapes of the JSON served by the Night Audit API (skeleton/src/nightaudit/models.py and report.py).
// Every amount is a decimal string. It is displayed with moneyText() and never converted to a float.

export type LedgerName = "intended" | "observed" | "billed";
export const LEDGERS: readonly LedgerName[] = ["intended", "observed", "billed"];

export interface EvidenceRecord {
  ledger: LedgerName;
  source: string;
  row_id: string;
  raw_key: string;
  key: string | null;
  attrs: Record<string, string>;
  amount: string | null;
  timestamp: string | null;
}

export interface Finding {
  key: string;
  region_code: string;
  name: string;
  severity: string;
  meaning: string;
  informational: boolean;
  records: EvidenceRecord[];
  billed_amount: string;
  duplicate_counts: Record<string, number>;
  status: "new" | "persisting" | "resolved";
  nights_persisted: number | null;
  first_seen: string | null;
  explanation: string | null;
  context: Record<string, string>;
}

export interface RegionSummary {
  code: string;
  key_count: number;
  billed_amount: string;
}

export interface Snapshot {
  name: LedgerName;
  source: string;
  records: EvidenceRecord[];
  missing: boolean;
}

export interface UiColumn {
  label: string;
  from: string;
}

export interface UiConfig {
  title: string;
  tagline: string;
  noun: { singular: string; plural: string };
  ledgers: Record<string, { label: string; source: string }>;
  columns: UiColumn[];
  headlines: Record<string, { one: string; other: string }>;
  /** Words for billed lines with no key (Req 10.4). Absent in runs saved before it existed. */
  unkeyed?: { singular: string; plural: string; explanation: string };
  downloads?: Download[];
}

/** A file beside the run that the page links to (Req 10.6). */
export interface Download {
  label: string;
  file: string;
}

/** A sentence a summariser added to the run; every number in it is evidence (Req 10.2). */
export interface RunNote {
  text: string;
  numbers: string[];
  source: string;
}

/** A review decision recorded against a finding, shown only when its chain verifies (Req 10.7). */
export interface Decision {
  key: string;
  region_code: string;
  decision: string;
  decision_date: string;
  reviewer: string;
}

export interface Decisions {
  ok: boolean;
  detail: string;
  rows: Decision[];
}

/** An investigator's note on a finding. The page only receives accepted notes, and only when their chain verifies. */
export interface InvestigatorNote {
  key: string;
  region_code: string;
  text: string;
  model: string;
  at: string;
}

export interface InvestigatorNotes {
  ok: boolean;
  detail: string;
  rows: InvestigatorNote[];
}

export interface MoneyLine {
  label: string;
  value: string;
  amount: string;
  note: string;
}

export interface RunView {
  headline: string;
  headline_sentences: string[];
  calm: boolean;
  ledger_keys: Record<string, number | null>;
  keyed_total: string;
  unkeyed_total: string;
  billed_total: string;
  lines: MoneyLine[];
  finding_count: number;
  new_count: number;
  persisting_count: number;
  pending_count: number;
  resolved_count: number;
}

export interface RunResult {
  run_id: string;
  run_time: string;
  control_hash: string;
  control_id: string;
  control_title: string;
  app: string;
  complete: boolean;
  missing_ledgers: string[];
  ledger_errors: Record<string, string>;
  snapshots: Snapshot[];
  regions: Record<string, string>;
  region_names: Record<string, string>;
  /** Each region's short plain label. Absent in runs saved before labels existed. */
  region_labels?: Record<string, string>;
  region_meanings: Record<string, string>;
  region_summaries: Record<string, RegionSummary>;
  pending_keys: string[];
  findings: Finding[];
  resolved: Finding[];
  billed_total: string;
  billed_unkeyed: string;
  evidence_chain_hash: string | null;
  ui: UiConfig;
  view: RunView;
  notes?: RunNote[];
  /** The downloads that exist beside this run. */
  downloads?: Download[];
  decisions?: Decisions;
  /** The night shift's notes (night shift Req 1.2). Absent when the run has none. */
  investigator_notes?: InvestigatorNotes;
}

export interface RunSummary {
  run_id: string;
  run_time: string;
  control_id: string;
  control_title: string;
  app: string;
  complete: boolean;
  findings: number;
  new_findings?: number;
  informational: number;
}

/** One entry of apps.json, written at build time. `base` is where that app's data lives, relative to the page. */
export interface AppEntry {
  name: string;
  title: string;
  mode: "live" | "demo";
  base: string;
}

/** The seven region codes, in the order the page lists them. */
export const REGION_ORDER = ["OB", "B", "IB", "O", "I", "IO", "IOB"] as const;
export const REGION_CODES: ReadonlySet<string> = new Set(REGION_ORDER);
