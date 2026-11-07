// Recompute an evidence pack's hash chain in the browser with WebCrypto. Step for step the same as
// verify_evidence_pack in skeleton/src/nightaudit/evidence.py, so both give the same verdict on the same pack
// (ui-kit Req 6.1, 6.4). This module is built as the stable chunk assets/verify.js.

import { byCodePoint, canonical, pyStr } from "./canonical";
import { headlineMoneyText, moneyText } from "./format";

export const CHAIN_SEED = "0".repeat(64);
const CONTENT_FIELDS = ["ledger", "row_id", "raw_key", "key", "attrs", "amount", "timestamp"] as const;
/** The manifest fields the header row repeats (HEADER_FIELDS in evidence.py). */
const HEADER_FIELDS = ["run_id", "run_time", "control_hash", "row_count", "finding_count", "complete"] as const;
/** The three ledgers. A night that could not read one of them writes no record row for it. */
const LEDGERS = ["intended", "observed", "billed"] as const;
/** Regions whose findings are informational (INFORMATIONAL_REGIONS in models.py). */
const INFORMATIONAL = new Set(["IO"]);
const MAX_PROBLEMS = 8;

type Row = Record<string, unknown>;

export interface VerifyResult {
  ok: boolean;
  detail: string;
  failedRow: number | null;
  rows: number;
  findings: number;
  finalHash: string | null;
  /** True when the chain starts with a header row naming the run. Packs from before that row verify without one. */
  hasHeader: boolean;
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
  return { ok: false, detail, failedRow, rows: 0, findings: 0, finalHash: null, hasHeader: false };
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
  displayed?: Row,
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
  // The manifest names exactly the three ledgers, and every record row belongs to one of them (evidence.py).
  for (let i = 0; i < rows.length; i += 1) {
    const ledger = get(rows[i], "ledger");
    if (get(rows[i], "type") === "record" && !(LEDGERS as readonly unknown[]).includes(ledger)) {
      return fail(`row ${i}: record of ledger ${canonical(ledger)}, which is not intended, observed or billed`, i);
    }
  }
  if (!isObject(ledgers)) return fail("manifest 'ledgers' is not an object");
  const names = Object.keys(ledgers).sort(byCodePoint);
  if (names.length !== LEDGERS.length || !LEDGERS.every((name) => has(ledgers, name))) {
    return fail(`manifest ledgers are billed, intended, observed: it names ${names.join(", ") || "none"}`);
  }
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
  const headerFailure = checkHeader(rows, manifest, findingRows);
  if (headerFailure) return headerFailure;
  const hasHeader = rows.length > 0 && get(rows[0], "type") === "header";
  let detail = `verified ${rows.length} rows, ${findingRows} findings`;
  detail += hasHeader
    ? ", header matches the manifest"
    : "; this pack carries no header row, so its run id and run time are not bound to the chain";
  if (displayed !== undefined) {
    const problems = compareDisplayed(displayed, manifest, rows, prev);
    if (problems.length) return fail(displayFailure(problems));
    detail += "; the page matches the evidence";
  }
  return { ok: true, detail, failedRow: null, rows: rows.length, findings: findingRows, finalHash: prev, hasHeader };
}

function checkHeader(rows: Row[], manifest: Row, findingRows: number): VerifyResult | null {
  for (let i = 0; i < rows.length; i += 1) {
    if (get(rows[i], "type") === "header" && i !== 0) return fail(`row ${i}: a header row must be the first row`, i);
  }
  if (!rows.length || get(rows[0], "type") !== "header") return null;
  const header = rows[0];
  for (const field of HEADER_FIELDS) {
    const inManifest = canonical(get(manifest, field));
    const inHeader = canonical(get(header, field));
    if (inManifest !== inHeader) {
      return fail(`manifest ${field} differs from the chain header (manifest ${inManifest}, header ${inHeader})`);
    }
  }
  if (canonical(get(header, "row_count")) !== canonical(rows.length)) {
    return fail(`chain header says ${canonical(get(header, "row_count"))} rows, the chain has ${rows.length}`);
  }
  if (canonical(get(header, "finding_count")) !== canonical(findingRows)) {
    return fail(`chain header says ${canonical(get(header, "finding_count"))} findings, the chain has ${findingRows}`);
  }
  if (has(header, "complete") && typeof header.complete !== "boolean") {
    return fail(`chain header says the night was complete ${canonical(header.complete)}, which is not true or false`);
  }
  return null;
}

/** Whether the night was complete, as the chain's header row records it (chain_completeness in evidence.py). A pack
 * that does not record it is taken as complete. */
export function chainCompleteness(rows: Row[]): boolean | null {
  if (rows.length && get(rows[0], "type") === "header") {
    const value = get(rows[0], "complete");
    if (typeof value === "boolean") return value;
  }
  return null;
}

// --- What the page displays, against what the chain holds (compare_displayed in evidence.py, sentence for sentence) ---

/** The same pattern as _DECIMAL_TEXT in evidence.py. */
const DECIMAL_TEXT = /^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/;
const DECIMAL_PARTS = /^([+-]?)([0-9]*)\.?([0-9]*)(?:[eE]([+-]?[0-9]+))?$/;
const MAX_EXPONENT_SPREAD = 100000;

/** An exact decimal: coef * 10^exp. */
interface Dec {
  coef: bigint;
  exp: number;
}

function decimal(value: unknown): Dec | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const text = String(value);
  if (!DECIMAL_TEXT.test(text)) return null;
  const m = DECIMAL_PARTS.exec(text);
  if (!m) return null;
  const coef = BigInt(m[2] + m[3]) * (m[1] === "-" ? -1n : 1n);
  return { coef, exp: Number(m[4] ?? "0") - m[3].length };
}

function aligned(a: Dec, b: Dec): [bigint, bigint, number] {
  const exp = Math.min(a.exp, b.exp);
  if (Math.max(a.exp, b.exp) - exp > MAX_EXPONENT_SPREAD) throw new RangeError("amounts too far apart in size to compare");
  return [a.coef * 10n ** BigInt(a.exp - exp), b.coef * 10n ** BigInt(b.exp - exp), exp];
}

const same = (a: Dec, b: Dec): boolean => {
  const [x, y] = aligned(a, b);
  return x === y;
};

function add(a: Dec, b: Dec): Dec {
  const [x, y, exp] = aligned(a, b);
  return { coef: x + y, exp };
}

const ZERO: Dec = { coef: 0n, exp: 0 };
const decText = (d: Dec): string => moneyText(`${d.coef}E${d.exp}`);

function amountText(value: unknown): string {
  const d = decimal(value);
  return d ? decText(d) : canonical(value);
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

function sameInstant(a: unknown, b: unknown): boolean {
  if (canonical(a) === canonical(b)) return true;
  if (typeof a !== "string" || typeof b !== "string") return false;
  const zone = /(?:Z|[+-][0-9]{2}:?[0-9]{2})$/;
  if (!zone.test(a) || !zone.test(b)) return false;
  const x = Date.parse(a);
  const y = Date.parse(b);
  return !Number.isNaN(x) && !Number.isNaN(y) && x === y;
}

function has(obj: Row, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

export function compareDisplayed(displayed: Row, manifest: Row, rows: Row[], finalHash: string): string[] {
  const q = canonical;
  const problems: string[] = [];

  for (const field of ["run_id", "run_time", "control_hash"]) {
    if (has(manifest, field)) {
      const shown = get(displayed, field);
      const ok = field === "run_time" ? sameInstant(shown, manifest[field]) : q(shown) === q(manifest[field]);
      if (!ok) problems.push(`${field}: the page shows ${q(shown)}, the evidence has ${q(manifest[field])}`);
    }
  }
  const shownHash = get(displayed, "evidence_chain_hash");
  if (q(shownHash) !== q(finalHash)) {
    problems.push(`evidence chain hash: the page shows ${q(shownHash)}, the chain ends ${q(finalHash)}`);
  }

  const chainFindings = rows.filter((r) => get(r, "type") === "finding");
  const chainByKey = new Map<string, Row>();
  for (const row of chainFindings) {
    const key = pyStr(get(row, "key"));
    if (!chainByKey.has(key)) chainByKey.set(key, row);
  }
  const shownList = get(displayed, "findings");
  const shownFindings = Array.isArray(shownList) ? shownList.filter(isObject) : [];
  if (!Array.isArray(shownList) || shownFindings.length !== shownList.length) {
    problems.push("findings: the page does not hold a list of findings");
  }
  const seen = new Set<string>();
  for (const finding of shownFindings) {
    const key = get(finding, "key");
    const name = q(key);
    if (typeof key !== "string" || !chainByKey.has(key)) {
      problems.push(`finding ${name} is shown but is not in the evidence`);
      continue;
    }
    if (seen.has(key)) {
      problems.push(`finding ${name} is shown more than once`);
      continue;
    }
    seen.add(key);
    const row = chainByKey.get(key) as Row;
    if (q(get(finding, "region_code")) !== q(get(row, "region_code"))) {
      problems.push(
        `finding ${name}: the page shows region ${q(get(finding, "region_code"))}, the evidence has ${q(get(row, "region_code"))}`,
      );
    }
    if (q(get(finding, "status")) !== q(get(row, "status"))) {
      problems.push(
        `finding ${name}: the page shows status ${q(get(finding, "status"))}, the evidence has ${q(get(row, "status"))}`,
      );
    }
    const shownAmount = decimal(get(finding, "billed_amount"));
    const chainAmount = decimal(get(row, "billed_amount"));
    if (!shownAmount || !chainAmount || !same(shownAmount, chainAmount)) {
      problems.push(
        `finding ${name}: the page shows billed amount ${amountText(get(finding, "billed_amount"))}, the evidence has ${amountText(get(row, "billed_amount"))}`,
      );
    }
  }
  const shownKeys = new Set(shownFindings.map((f) => get(f, "key")));
  for (const key of chainByKey.keys()) {
    if (!shownKeys.has(key)) problems.push(`finding ${q(key)} is in the evidence but is not shown`);
  }

  const counts = new Map<string, number>();
  const amounts = new Map<string, Dec>();
  for (const row of chainFindings) {
    const code = pyStr(get(row, "region_code"));
    counts.set(code, (counts.get(code) ?? 0) + 1);
    amounts.set(code, add(amounts.get(code) ?? ZERO, decimal(get(row, "billed_amount")) ?? ZERO));
  }
  const summaries = get(displayed, "region_summaries");
  const shownRegions: Row = isObject(summaries) ? summaries : {};
  const codes = [...new Set([...Object.keys(shownRegions), ...counts.keys()])].filter((c) => c !== "IOB").sort(byCodePoint);
  for (const code of codes) {
    const raw = has(shownRegions, code) ? shownRegions[code] : undefined;
    const entry: Row = isObject(raw) ? raw : {};
    const shownCount = get(entry, "key_count", 0);
    const chainCount = counts.get(code) ?? 0;
    if (count(shownCount) !== chainCount) {
      problems.push(`region ${code}: the page counts ${q(shownCount)}, the evidence has ${chainCount}`);
    }
    const shownAmount = decimal(get(entry, "billed_amount", "0"));
    const chainAmount = amounts.get(code) ?? ZERO;
    if (!shownAmount || !same(shownAmount, chainAmount)) {
      problems.push(
        `region ${code}: the page bills ${amountText(get(entry, "billed_amount", "0"))}, the evidence has ${decText(chainAmount)}`,
      );
    }
  }

  let total = ZERO;
  let unkeyed = ZERO;
  for (const row of rows) {
    if (get(row, "type") !== "record" || get(row, "ledger") !== "billed") continue;
    const amount = decimal(get(row, "amount"));
    if (!amount) continue;
    total = add(total, amount);
    if (get(row, "key") === null) unkeyed = add(unkeyed, amount);
  }
  // Completeness comes from the chain. A pack that does not record it is taken as complete: nothing in it can prove that
  // a ledger went unread.
  const shownComplete = get(displayed, "complete");
  const chainComplete = chainCompleteness(rows);
  let incomplete = false;
  if (chainComplete !== null) {
    if (q(shownComplete) !== q(chainComplete)) {
      problems.push(`complete: the page shows ${q(shownComplete)}, the evidence has ${q(chainComplete)}`);
    }
    incomplete = chainComplete === false;
  } else if (shownComplete !== true) {
    problems.push(
      `complete: the page shows ${q(shownComplete)}, the evidence records no completeness, so the night is taken as complete`,
    );
  }
  if (incomplete) {
    // An incomplete run matches nothing and states no amount (Req 9.4): the page must show zero.
    total = ZERO;
    unkeyed = ZERO;
  }
  const view = get(displayed, "view");
  const figures: [string, unknown, Dec][] = [
    ["billed total", get(displayed, "billed_total"), total],
    ["unkeyed billed amount", get(displayed, "billed_unkeyed"), unkeyed],
  ];
  if (isObject(view)) {
    figures.push(
      ["headline billed total", get(view, "billed_total"), total],
      ["headline unkeyed amount", get(view, "unkeyed_total"), unkeyed],
      ["headline keyed amount", get(view, "keyed_total"), add(total, { coef: -unkeyed.coef, exp: unkeyed.exp })],
    );
  }
  for (const [label, shown, expected] of figures) {
    const number = decimal(shown);
    if (!number || !same(number, expected)) {
      problems.push(`${label}: the page shows ${amountText(shown)}, the evidence has ${decText(expected)}`);
    }
  }
  if (isObject(view)) {
    const headline = chainFindings.filter((r) => !INFORMATIONAL.has(pyStr(get(r, "region_code"))));
    const checks: [string, string, number][] = [
      ["headline finding count", "finding_count", headline.length],
      ["headline new count", "new_count", headline.filter((r) => get(r, "status") === "new").length],
      ["headline persisting count", "persisting_count", headline.filter((r) => get(r, "status") === "persisting").length],
    ];
    for (const [label, field, expected] of checks) {
      if (count(get(view, field)) !== expected) {
        problems.push(`${label}: the page shows ${q(get(view, field))}, the evidence has ${expected}`);
      }
    }
    problems.push(...headlineProblems(view, counts, amounts));
  }
  return problems;
}

/** Headline order (HEADLINE_ORDER in report.py): the regions whose count and amount the headline may print. */
const HEADLINE_REGIONS = ["OB", "B", "IB", "O", "I"] as const;
/** An amount as the page prints it in prose (_MONEY_TOKEN in evidence.py). */
const MONEY_TOKEN = /[\u2212-]?\$[0-9][0-9,]*(?:\.[0-9]+)?/g;
/**
 * A number in text: the explanation guard's scanner (_NUM_RE in explain.py). Python's \w and \d are Unicode, so the
 * lookbehind is written with Unicode classes; a digit that is not 0 to 9 is refused before this runs.
 */
const NUMBER = /(?:(?<![\p{L}\p{N}_.])[-\u2212])?[0-9]+(?:\.[0-9]+)?/gu;
const OTHER_DIGIT = /(?![0-9])\p{Decimal_Number}/u;

/** Every number in text as written, in order, its minus written "-" (number_literals in explain.py). */
export function numberLiterals(text: string): string[] {
  return (text.match(NUMBER) ?? []).map((n) => n.replace("\u2212", "-"));
}

/**
 * Each number the headline prints must be one of its own: a headline region's count, or its amount written exactly or
 * rounded the headline's way. Money tokens are compared as text, and every numeric literal as a number.
 */
function headlineProblems(view: Row, counts: Map<string, number>, amounts: Map<string, Dec>): string[] {
  const allowed = new Set<string>();
  const allowedNumbers: Dec[] = [];
  for (const code of HEADLINE_REGIONS) {
    const n = counts.get(code);
    if (n !== undefined) allowedNumbers.push({ coef: BigInt(n), exp: 0 });
    const amount = amounts.get(code);
    if (!amount) continue;
    const text = `${amount.coef}E${amount.exp}`;
    for (const printed of [moneyText(text), headlineMoneyText(text)]) {
      allowed.add(printed);
      for (const literal of numberLiterals(printed)) allowedNumbers.push(decimal(literal) as Dec);
    }
  }
  const sentences = get(view, "headline_sentences");
  const texts = Array.isArray(sentences) ? sentences.filter((s): s is string => typeof s === "string") : [];
  const lead = get(view, "headline");
  if (typeof lead === "string") texts.push(lead);
  const problems: string[] = [];
  if (texts.some((t) => OTHER_DIGIT.test(t))) problems.push("headline: the page shows a digit that is not 0 to 9");
  const tokens = new Set(texts.flatMap((text) => text.match(MONEY_TOKEN) ?? []));
  for (const t of tokens) {
    if (!allowed.has(t)) problems.push(`headline: the page shows ${t}, which is no region's amount in the evidence`);
  }
  const refused: string[] = [];
  for (const literal of texts.flatMap(numberLiterals)) {
    const n = decimal(literal) as Dec;
    if (!allowedNumbers.some((a) => same(a, n)) && !refused.includes(literal)) refused.push(literal);
  }
  for (const n of refused) {
    problems.push(`headline: the page shows the number ${n}, which is not one of the headline's counts or amounts`);
  }
  return problems;
}

function displayFailure(problems: string[]): string {
  const shown = problems.slice(0, MAX_PROBLEMS).join("; ");
  const more = problems.length - MAX_PROBLEMS;
  return `the page differs from the evidence: ${shown}${more > 0 ? `; and ${more} more` : ""}`;
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
