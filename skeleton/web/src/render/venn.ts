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
  IO: [220, 104],
  IB: [146, 230],
  OB: [294, 230],
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

/** A region label is drawn on up to three short lines inside its region ("Running and / billed, never / approved"),
 * filled word by word so no line is longer than NAME_FITS characters unless one word is. A short label stays on one
 * line. The lens regions are about 60 to 100 units wide, which holds 13 characters at the label's size. */
export const NAME_FITS = 13;
export const NAME_LINES = 3;
export function nameLines(name: string): string[] {
  const lines: string[] = [];
  for (const word of name.split(" ").filter(Boolean)) {
    const last = lines.length ? lines[lines.length - 1] : null;
    if (last !== null && (last + " " + word).length <= NAME_FITS) lines[lines.length - 1] = `${last} ${word}`;
    else lines.push(word);
  }
  if (lines.length <= NAME_LINES) return lines;
  // Never drop words: anything past the last line joins it.
  return [...lines.slice(0, NAME_LINES - 1), lines.slice(NAME_LINES - 1).join(" ")];
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
      const name = input.names[code] ?? code;
      const lines = nameLines(name);
      const lift = (lines.length - 1) * 11; // later lines would cross into the region below
      return `<text class="venn-count${tone}${sel}" x="${x}" y="${y - lift}" text-anchor="middle">${n}</text>
        ${lines.map((line, i) => `<text class="venn-name${sel}" x="${x}" y="${y - lift + 16 + i * 12}" text-anchor="middle">${esc(line)}</text>`).join("")}`;
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
