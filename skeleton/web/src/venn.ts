// The three-ledger Venn diagram. It is both the summary and the navigation: a region click filters the rows.
// Mouse clicks are hit-tested against the circles; keyboard users use the region legend (same handler).

const R = 115;
export const CIRCLES = {
  I: { cx: 165, cy: 150, label: "INTENDED", lx: 70, ly: 34 },
  O: { cx: 275, cy: 150, label: "OBSERVED", lx: 370, ly: 34 },
  B: { cx: 220, cy: 245, label: "BILLED", lx: 220, ly: 382 },
} as const;

const LABEL_AT: Record<string, [number, number]> = {
  I: [112, 128],
  O: [328, 128],
  B: [220, 312],
  IO: [220, 102],
  IB: [158, 222],
  OB: [282, 222],
  IOB: [220, 178],
};

type Letter = keyof typeof CIRCLES;
const LETTERS: Letter[] = ["I", "O", "B"];

export function regionAt(x: number, y: number): string | null {
  const code = LETTERS.filter((l) => {
    const c = CIRCLES[l];
    return (x - c.cx) ** 2 + (y - c.cy) ** 2 <= R * R;
  }).join("");
  return code || null;
}

function fillFor(code: string, count: number, selected: boolean): string {
  if (count === 0) return selected ? "rgba(124,255,178,0.10)" : "transparent";
  if (code === "IOB") return selected ? "rgba(124,255,178,0.30)" : "rgba(124,255,178,0.12)";
  if (code === "IO") return selected ? "rgba(201,211,255,0.32)" : "rgba(201,211,255,0.12)";
  const base = selected ? 0.38 : 0.13;
  return `rgba(255,179,71,${Math.min(base + count * 0.02, 0.5)})`;
}

export interface VennInput {
  counts: Record<string, number>;
  names: Record<string, string>;
  selected: string | null;
  ledgerTotals: Record<string, number>;
}

export function vennSvg(input: VennInput): string {
  const defs = LETTERS.map((l) => {
    const c = CIRCLES[l];
    return `<clipPath id="clip-${l}"><circle cx="${c.cx}" cy="${c.cy}" r="${R}"/></clipPath>
      <mask id="not-${l}"><rect x="0" y="0" width="440" height="400" fill="white"/><circle cx="${c.cx}" cy="${c.cy}" r="${R}" fill="black"/></mask>`;
  }).join("");

  const regions = Object.keys(LABEL_AT)
    .map((code) => {
      const present = LETTERS.filter((l) => code.includes(l));
      const absent = LETTERS.filter((l) => !code.includes(l));
      let shape = `<rect x="0" y="0" width="440" height="400" fill="${fillFor(code, input.counts[code] ?? 0, input.selected === code)}"/>`;
      for (const a of absent) shape = `<g mask="url(#not-${a})">${shape}</g>`;
      for (const p of present) shape = `<g clip-path="url(#clip-${p})">${shape}</g>`;
      return shape;
    })
    .join("");

  const outlines = LETTERS.map((l) => {
    const c = CIRCLES[l];
    return `<circle class="venn-ring" cx="${c.cx}" cy="${c.cy}" r="${R}"/>`;
  }).join("");

  const ledgerLabels = LETTERS.map((l) => {
    const c = CIRCLES[l];
    const name = l === "I" ? "intended" : l === "O" ? "observed" : "billed";
    const total = input.ledgerTotals[name];
    return `<text class="venn-ledger" x="${c.lx}" y="${c.ly}" text-anchor="middle">${c.label}${
      total === undefined ? "" : ` · ${total}`
    }</text>`;
  }).join("");

  const labels = Object.entries(LABEL_AT)
    .map(([code, [x, y]]) => {
      const n = input.counts[code] ?? 0;
      const cls = n > 0 && code !== "IOB" && code !== "IO" ? "venn-count hot" : "venn-count";
      const name = (input.names[code] ?? code).toUpperCase();
      return `<text class="${cls}" x="${x}" y="${y}" text-anchor="middle">${n}</text>
        <text class="venn-name" x="${x}" y="${y + 17}" text-anchor="middle">${name}</text>`;
    })
    .join("");

  return `<svg class="venn" viewBox="0 0 440 400" role="img" aria-labelledby="venn-title">
    <title id="venn-title">Keys by region across the intended, observed and billed ledgers</title>
    <defs>${defs}</defs>${regions}${outlines}${ledgerLabels}${labels}</svg>`;
}
