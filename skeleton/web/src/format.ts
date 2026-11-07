// Formatting. Every value from a ledger is untrusted text and goes through esc() before it enters markup.
// Money is displayed from the decimal strings the API sends; it is never converted to a float.

export function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const DECIMAL = /^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/;

/**
 * An amount shown exactly, by the same rules as money_text in skeleton/src/nightaudit/report.py: `$1,234.50`,
 * `−$3.10` (U+2212), `$0.000000001`, `$0.00` for any zero. Works on the decimal string, character by character.
 */
export function moneyText(amount: string | null | undefined): string {
  if (amount === null || amount === undefined) return "";
  const m = DECIMAL.exec(amount.trim());
  if (!m || (m[2] === "" && (m[3] ?? "") === "")) return amount;
  const intDigits = m[2];
  const digits = intDigits + (m[3] ?? "");
  const point = intDigits.length + Number(m[4] ?? "0");
  let whole: string;
  let fraction: string;
  if (point <= 0) {
    whole = "0";
    fraction = "0".repeat(-point) + digits;
  } else if (point >= digits.length) {
    whole = digits + "0".repeat(point - digits.length);
    fraction = "";
  } else {
    whole = digits.slice(0, point);
    fraction = digits.slice(point);
  }
  whole = whole.replace(/^0+(?=\d)/, "");
  fraction = fraction.replace(/0+$/, "");
  if (whole === "0" && fraction === "") return "$0.00";
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${m[1] === "-" ? "\u2212" : ""}$${grouped}.${fraction.padEnd(2, "0")}`;
}

/** The headline shows an amount to this many significant figures (HEADLINE_FIGURES in report.py). */
const HEADLINE_FIGURES = 4;

/**
 * An amount as the headline prints it, by the same rule as headline_money_text in report.py: rounded half-even to four
 * significant figures, never coarser than a cent. `0.7172358001` is `$0.7172`, `0.71725` is `$0.7172`. BigInt only.
 */
export function headlineMoneyText(amount: string): string {
  const m = DECIMAL.exec(amount.trim());
  if (!m || (m[2] === "" && (m[3] ?? "") === "")) return moneyText(amount);
  const negative = m[1] === "-";
  let coef = BigInt((m[2] + (m[3] ?? "")).replace(/^0+(?=\d)/, "") || "0");
  let exp = Number(m[4] ?? "0") - (m[3] ?? "").length;
  if (coef !== 0n) {
    const adjusted = exp + coef.toString().length - 1;
    const target = Math.min(adjusted - (HEADLINE_FIGURES - 1), -2);
    if (exp < target) {
      const p = 10n ** BigInt(target - exp);
      let q = coef / p;
      const twice = (coef % p) * 2n;
      if (twice > p || (twice === p && q % 2n === 1n)) q += 1n;
      coef = q;
      exp = target;
    }
  }
  return moneyText(`${negative ? "-" : ""}${coef}E${exp}`);
}

/** True when a decimal string is below zero, without converting it to a number. */
export function isNegative(amount: string | null | undefined): boolean {
  return moneyText(amount).startsWith("\u2212");
}

/** True when a decimal string is zero, without converting it to a number. */
export function isZero(amount: string | null | undefined): boolean {
  return moneyText(amount) === "$0.00";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function utc(iso: string): Date | null {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

const two = (n: number): string => String(n).padStart(2, "0");

/** `06 Nov 2026` in UTC, the same as date_text in report.py. */
export function dateText(iso: string | null | undefined): string {
  const d = iso ? utc(iso) : null;
  return d ? `${two(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}` : "";
}

/** `06 NOV` for the nights strip. */
export function dayText(iso: string): string {
  const d = utc(iso);
  return d ? `${two(d.getUTCDate())} ${MONTHS[d.getUTCMonth()].toUpperCase()}` : "";
}

/** `02:00 UTC · 06 Nov 2026`. */
export function stampText(iso: string): string {
  const d = utc(iso);
  return d ? `${two(d.getUTCHours())}:${two(d.getUTCMinutes())} UTC · ${dateText(iso)}` : "";
}

export function plural(n: number, one: string, other: string): string {
  return `${n} ${n === 1 ? one : other}`;
}
