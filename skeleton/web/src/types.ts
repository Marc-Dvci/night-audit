// Shapes of the JSON served by the Night Audit API (skeleton/src/nightaudit/models.py).

export type LedgerName = "intended" | "observed" | "billed";

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
  region_summaries: Record<string, RegionSummary>;
  pending_keys: string[];
  unkeyed: { row_id: string; ledger: LedgerName; source: string; amount: string | null }[];
  findings: Finding[];
  resolved: Finding[];
  billed_total: string;
  billed_unkeyed: string;
  dropped: Record<string, number>;
  excluded: Record<string, number>;
  evidence_chain_hash: string | null;
}

export interface RunSummary {
  run_id: string;
  run_time: string;
  control_id: string;
  control_title: string;
  app: string;
  complete: boolean;
  findings: number;
  informational: number;
}

export const REGION_ORDER = ["OB", "B", "IB", "I", "O", "IO", "IOB"] as const;
