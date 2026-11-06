// Recompute an evidence pack's hash chain in the browser with WebCrypto. Step for step the same as
// verify_evidence_pack in skeleton/src/nightaudit/evidence.py, so both give the same verdict on the same pack
// (ui-kit Req 6.1, 6.4). This module is built as the stable chunk assets/verify.js.

import { byCodePoint, canonical, pyStr } from "./canonical";

export const CHAIN_SEED = "0".repeat(64);
const CONTENT_FIELDS = ["ledger", "row_id", "raw_key", "key", "attrs", "amount", "timestamp"] as const;

type Row = Record<string, unknown>;

export interface VerifyResult {
  ok: boolean;
  detail: string;
  failedRow: number | null;
  rows: number;
  findings: number;
  finalHash: string | null;
}

export interface RowProgress {
  index: number;
  type: string;
  ledger: string;
  rowId: string;
  hash: string;
}

const encoder = new TextEncoder();

export async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function get(row: Row, key: string, fallback: unknown = null): unknown {
  return Object.prototype.hasOwnProperty.call(row, key) ? row[key] : fallback;
}

function fail(detail: string, failedRow: number | null = null): VerifyResult {
  return { ok: false, detail, failedRow, rows: 0, findings: 0, finalHash: null };
}

function isObject(value: unknown): value is Row {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Verify evidence.jsonl text against its manifest. `onRow` is called after each row's hash is confirmed, so a caller can
 * print the rows as they are checked.
 */
export async function verifyPack(
  jsonl: string,
  manifest: Row,
  onRow?: (progress: RowProgress) => void | Promise<void>,
): Promise<VerifyResult> {
  const lines = jsonl.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();

  const rows: Row[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    let row: unknown;
    try {
      row = JSON.parse(lines[i]);
    } catch {
      return fail(`row ${i}: not valid JSON`, i);
    }
    if (!isObject(row)) return fail(`row ${i}: not a JSON object`, i);
    // Byte-exact: the stored line must be the canonical serialisation of its content.
    if (canonical(row) !== lines[i]) return fail(`row ${i}: bytes differ from the canonical form`, i);
    rows.push(row);
  }

  const seed = pyStr(get(manifest, "chain_seed", CHAIN_SEED));
  let prev = seed;
  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i];
    const without: Row = {};
    for (const [k, v] of Object.entries(row)) if (k !== "row_hash") without[k] = v;
    const storedPrev = pyStr(get(row, "prev_hash", ""));
    const recomputed = await sha256(storedPrev + canonical(without));
    const stored = pyStr(get(row, "row_hash", ""));
    if (recomputed !== stored) {
      return fail(`row ${i}: hash mismatch (stored ${stored.slice(0, 12)}, computed ${recomputed.slice(0, 12)})`, i);
    }
    const expectedPrev = i === 0 ? seed : prev;
    if (storedPrev !== expectedPrev) return fail(`row ${i}: chain broken (prev_hash does not link to previous row)`, i);
    prev = recomputed;
    if (onRow) {
      await onRow({
        index: i,
        type: pyStr(get(row, "type", "")),
        ledger: pyStr(get(row, "ledger", get(row, "region_code", ""))),
        rowId: pyStr(get(row, "row_id", get(row, "key", ""))),
        hash: recomputed,
      });
    }
  }

  const finalHash = pyStr(get(manifest, "final_chain_hash", ""));
  if (prev !== finalHash) {
    return fail(`final chain hash mismatch (manifest ${finalHash.slice(0, 12)}, computed ${prev.slice(0, 12)})`);
  }

  const ledgers = get(manifest, "ledgers", {});
  if (!isObject(ledgers)) return fail("manifest 'ledgers' is not an object");
  const byLedger = new Map<string, Row[]>();
  for (const row of rows) {
    if (get(row, "type") !== "record") continue;
    const name = pyStr(get(row, "ledger", ""));
    byLedger.set(name, [...(byLedger.get(name) ?? []), row]);
  }
  for (const [name, entry] of Object.entries(ledgers)) {
    if (!isObject(entry)) return fail(`ledger '${name}' entry is not an object`);
    // Array.prototype.sort is stable, like Python's sorted(), so rows with equal ids keep their file order.
    const ledgerRows = [...(byLedger.get(name) ?? [])].sort((a, b) =>
      byCodePoint(pyStr(get(a, "row_id", "")), pyStr(get(b, "row_id", ""))),
    );
    const contents = ledgerRows.map((r) => {
      const content: Row = {};
      for (const field of CONTENT_FIELDS) content[field] = get(r, field);
      return content;
    });
    const hash = await sha256(canonical(contents));
    if (hash !== pyStr(get(entry, "hash", ""))) return fail(`ledger '${name}': hash mismatch`);
    const count = Number(get(entry, "count", -1));
    if (count !== ledgerRows.length) return fail(`ledger '${name}': count mismatch (${count} vs ${ledgerRows.length})`);
  }

  const findingRows = rows.filter((r) => get(r, "type") === "finding").length;
  if (Object.prototype.hasOwnProperty.call(manifest, "finding_count") && Number(manifest.finding_count) !== findingRows) {
    return fail("finding count differs from the manifest");
  }
  return {
    ok: true,
    detail: `verified ${rows.length} rows, ${findingRows} findings`,
    failedRow: null,
    rows: rows.length,
    findings: findingRows,
    finalHash: prev,
  };
}

/** Change one character of one row, in memory only: the middle record row's raw_key, to a different character. */
export function changeOneByte(jsonl: string): { text: string; row: number; before: string; after: string } | null {
  const lines = jsonl.split("\n");
  const records = lines.map((line, i) => ({ line, i })).filter(({ line }) => line.includes('"type":"record"'));
  const target = records[Math.floor(records.length / 2)];
  if (!target) return null;
  const marker = '"raw_key":"';
  const start = target.line.indexOf(marker);
  if (start < 0) return null;
  const at = start + marker.length;
  const before = target.line[at];
  if (before === undefined || before === '"' || before === "\\") return null;
  const after = before === "x" ? "y" : "x";
  lines[target.i] = target.line.slice(0, at) + after + target.line.slice(at + 1);
  return { text: lines.join("\n"), row: target.i, before, after };
}
