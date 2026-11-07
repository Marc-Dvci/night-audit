// The Python-written parity fixture. It is read with JSON.parse rather than imported, because Vite's JSON loader
// rejects the lone surrogate escapes (\ud800) that the fixture holds on purpose.
import { readFileSync } from "node:fs";

interface Verdict {
  ok: boolean;
  failed_row: number | null;
  rows: number;
  findings: number;
  final_hash: string | null;
  detail: string;
}

export interface Parity {
  canonical: { value: unknown; canonical: string }[];
  money: { amount: string; text: string; headline: string }[];
  pack: {
    manifest: Record<string, unknown>;
    legacy: { jsonl: string; manifest: Record<string, unknown>; verdict: Verdict };
    variants: { name: string; jsonl: string; verdict: Verdict }[];
    displayed: { name: string; document: Record<string, unknown>; verdict: Verdict }[];
    completeness: {
      name: string;
      jsonl: string;
      manifest: Record<string, unknown>;
      document: Record<string, unknown>;
      verdict: Verdict;
    }[];
    ledgers: { name: string; jsonl: string; manifest: Record<string, unknown>; verdict: Verdict }[];
  };
}

const fixture: Parity = JSON.parse(readFileSync(new URL("./fixtures/parity.json", import.meta.url), "utf-8"));
export default fixture;
