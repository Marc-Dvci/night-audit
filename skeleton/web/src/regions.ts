// How a region is named for a reader: its short plain label first, then its Halloween name as a small, quieter tag
// with its glyph (ui-identity). The label is what every heading, count and button reads; the tag is never needed.

import { esc } from "./format";
import { GLYPHS } from "./glyphs";
import type { RunResult } from "./types";

/** The default plain labels, the same as DEFAULT_REGION_LABELS in models.py. Used by runs saved before labels. */
export const DEFAULT_LABELS: Record<string, string> = {
  IOB: "Matched",
  IO: "Approved and present, not billed",
  IB: "Approved and billed, not seen",
  OB: "Exists and billed, never approved",
  I: "Approved, but absent",
  O: "Exists, never approved, not billed",
  B: "Billed, never approved, not seen",
};

/** The region's plain label in this run. */
export function regionLabel(run: RunResult, code: string): string {
  return run.region_labels?.[code] || DEFAULT_LABELS[code] || code;
}

/** The small tag: the glyph and the Halloween name. Empty when the name is the label (a control with plain names). */
export function regionTag(run: RunResult, code: string, name?: string): string {
  const tag = name ?? run.region_names[code] ?? "";
  if (!tag || tag === regionLabel(run, code)) return `<span class="region-tag">${GLYPHS[code] ?? ""}</span>`;
  return `<span class="region-tag">${GLYPHS[code] ?? ""}<span class="region-tag-name">${esc(tag)}</span></span>`;
}

/** Label then tag, as one inline group. */
export function regionNamed(run: RunResult, code: string, name?: string): string {
  return `<span class="region-label">${esc(regionLabel(run, code))}</span> ${regionTag(run, code, name)}`;
}
