// Canonical JSON, byte for byte the same as Python's json.dumps(obj, sort_keys=True, separators=(",", ":")) with its
// default ensure_ascii=True (skeleton/src/nightaudit/evidence.py). JSON.stringify differs in three ways that matter:
// it leaves non-ASCII unescaped, it does not escape DEL (0x7F), and it keeps insertion order instead of sorting keys
// by code point.

const SHORT: Record<number, string> = { 0x22: '\\"', 0x5c: "\\\\", 0x08: "\\b", 0x0c: "\\f", 0x0a: "\\n", 0x0d: "\\r", 0x09: "\\t" };

/** A JSON string literal as Python writes it: every UTF-16 code unit outside 0x20-0x7E is escaped. */
export function pyString(value: string): string {
  let out = '"';
  for (let i = 0; i < value.length; i += 1) {
    const unit = value.charCodeAt(i);
    const short = SHORT[unit];
    if (short !== undefined) out += short;
    else if (unit >= 0x20 && unit <= 0x7e) out += value[i];
    else out += "\\u" + unit.toString(16).padStart(4, "0");
  }
  return out + '"';
}

/** Compare two strings by Unicode code point, as Python's sorted() does. UTF-16 order differs above U+FFFF. */
export function byCodePoint(a: string, b: string): number {
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i += 1) {
    const d = (x[i].codePointAt(0) ?? 0) - (y[i].codePointAt(0) ?? 0);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

/** Python's repr() of a float, for the values JSON.parse can produce. */
function pyNumber(n: number): string {
  if (!Number.isFinite(n)) return n > 0 ? "Infinity" : n < 0 ? "-Infinity" : "NaN";
  if (Number.isInteger(n) && Math.abs(n) < 1e16) return String(n);
  const text = String(n);
  return text.includes(".") || text.includes("e") ? text : `${text}.0`;
}

export function canonical(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return pyNumber(value);
  if (typeof value === "string") return pyString(value);
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => byCodePoint(a, b));
    return "{" + entries.map(([k, v]) => `${pyString(k)}:${canonical(v)}`).join(",") + "}";
  }
  throw new TypeError(`cannot serialise ${typeof value}`);
}

/** Python's str() of a parsed JSON value, used where the verifier compares stored fields as text. */
export function pyStr(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "number") return pyNumber(value);
  if (typeof value === "string") return value;
  return canonical(value);
}
