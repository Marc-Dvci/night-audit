// The three-ledger Venn diagram. It is both the summary and the navigation: a region click filters the rows.
// Mouse clicks are hit-tested against the circles; keyboard users use the region legend beside it (same handler).

import { esc } from "../format";

const R = 115;
const W = 440;
const H = 400;
export const CIRCLES = {
  I: { cx: 165, cy: 150, lx: 70, ly: 26, anchor: "middle" },
  O: { cx: 275, cy: 150, lx: 370, ly: 26, anchor: "middle" },
  B: { cx: 220, cy: 245, lx: 220, ly: 388, anchor: "middle" },
} as const;

const LABEL_AT: Record<string, [number, number]> = {
  I: [112, 128],
  O: [328, 128],
  B: [220, 312],
  IO: [220, 100],
  IB: [158, 222],
  OB: [282, 222],
  IOB: [220, 176],
};

type Letter = keyof typeof CIRCLES;
const LETTERS: Letter[] = ["I", "O", "B"];
const LEDGER_OF: Record<Letter, string> = { I: "intended", O: "observed", B: "billed" };

export function regionAt(x: number, y: number): string | null {
  const code = LETTERS.filter((l) => {
    const c = CIRCLES[l];
    return (x - c.cx) ** 2 + (y - c.cy) ** 2 <= R * R;
  }).join("");
  return code || null;
}

const capital = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

/** A region name longer than fits inside its region ("UNPROVISIONED JOINER") is drawn on two lines, split at a space
 * as near the middle as possible. Names of one word, or short names, stay on one line. */
export const NAME_FITS = 12;
export function nameLines(name: string): string[] {
  if (name.length <= NAME_FITS || !name.includes(" ")) return [name];
  const words = name.split(" ");
  let best = 1;
  for (let i = 1; i < words.length; i += 1) {
    const diff = (s: number): number => Math.abs(words.slice(0, s).join(" ").length - words.slice(s).join(" ").length);
    if (diff(i) < diff(best)) best = i;
  }
  return [words.slice(0, best).join(" "), words.slice(best).join(" ")];
}

export interface VennInput {
  counts: Record<string, number>;
  names: Record<string, string>;
  ledgerLabels: Record<string, string>;
  selected: string | null;
  calm: boolean;
  /** What the control counts, plural ("resources", "people"). */
  noun?: string;
}

function regionClass(code: string, count: number, selected: boolean): string {
  const kind = code === "IOB" ? "living" : code === "IO" ? "familiar" : "finding";
  return `venn-region ${kind}${count ? " has" : ""}${selected ? " selected" : ""}`;
}

export function vennSvg(input: VennInput): string {
  const defs = LETTERS.map((l) => {
    const c = CIRCLES[l];
    return `<clipPath id="clip-${l}"><circle cx="${c.cx}" cy="${c.cy}" r="${R}"/></clipPath>
      <mask id="not-${l}"><rect x="0" y="0" width="${W}" height="${H}" fill="white"/><circle cx="${c.cx}" cy="${c.cy}" r="${R}" fill="black"/></mask>`;
  }).join("");

  const regions = Object.keys(LABEL_AT)
    .map((code) => {
      const count = input.counts[code] ?? 0;
      let shape = `<rect class="${regionClass(code, count, input.selected === code)}" x="0" y="0" width="${W}" height="${H}"/>`;
      for (const a of LETTERS.filter((l) => !code.includes(l))) shape = `<g mask="url(#not-${a})">${shape}</g>`;
      for (const p of LETTERS.filter((l) => code.includes(l))) shape = `<g clip-path="url(#clip-${p})">${shape}</g>`;
      return shape;
    })
    .join("");

  const rings = LETTERS.map((l) => {
    const c = CIRCLES[l];
    return `<circle class="venn-ring" cx="${c.cx}" cy="${c.cy}" r="${R}"/>`;
  }).join("");

  const ledgerLabels = LETTERS.map((l) => {
    const c = CIRCLES[l];
    const label = (input.ledgerLabels[LEDGER_OF[l]] ?? LEDGER_OF[l]).toUpperCase();
    return `<text class="venn-ledger" x="${c.lx}" y="${c.ly}" text-anchor="${c.anchor}">${esc(label)}</text>`;
  }).join("");

  // In a calm night only the matched count is printed: a ring of zeros reads as an empty, broken page.
  const labels = Object.entries(LABEL_AT)
    .filter(([code]) => !input.calm || code === "IOB")
    .map(([code, [x, y]]) => {
      const n = input.counts[code] ?? 0;
      const tone = code === "IOB" ? " living" : code === "IO" ? "" : n > 0 ? " hot" : " zero";
      const sel = input.selected === code ? " sel" : "";
      const name = (input.names[code] ?? code).toUpperCase();
      const lines = nameLines(name);
      const lift = (lines.length - 1) * 12; // a second line would cross into the region below
      return `<text class="venn-count${tone}${sel}" x="${x}" y="${y - lift}" text-anchor="middle">${n}</text>
        ${lines.map((line, i) => `<text class="venn-name${sel}" x="${x}" y="${y - lift + 17 + i * 13}" text-anchor="middle">${esc(line)}</text>`).join("")}`;
    })
    .join("");

  const description = Object.keys(LABEL_AT)
    .map((code) => `${input.names[code] ?? code} ${input.counts[code] ?? 0}`)
    .join(", ");

  return `<svg class="venn${input.calm ? " calm" : ""}" viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="venn-title venn-desc">
    <title id="venn-title">${esc(capital(input.noun ?? "keys"))} by region across the three ledgers</title>
    <desc id="venn-desc">${esc(description)}</desc>
    <defs>${defs}</defs>${regions}${rings}${ledgerLabels}${labels}</svg>`;
}
