// The investigator's note under a finding (night shift Req 1.2): shown only when accepted and verified, escaped, and a
// finding without a note renders exactly as it did before notes existed.
import { describe, expect, it } from "vitest";
import { NOTE_LABEL, findings } from "../src/render/rows";
import type { Finding, InvestigatorNotes, RunResult } from "../src/types";

function finding(key: string, region = "OB"): Finding {
  return {
    key,
    region_code: region,
    name: "Vampire",
    severity: "high",
    meaning: "Exists and is paid for, but nobody approved it.",
    informational: false,
    records: [],
    billed_amount: "3.10",
    duplicate_counts: {},
    status: "new",
    nights_persisted: null,
    first_seen: null,
    explanation: "Exists and is paid for, but nobody approved it.",
    context: {},
  };
}

function run(notes?: InvestigatorNotes): RunResult {
  const base = {
    findings: [finding("i-0aa1"), finding("i-0bb2")],
    ui: { columns: [{ label: "Key", from: "key" }], noun: { singular: "instance", plural: "instances" } },
    region_names: { OB: "Vampire" },
    regions: {},
    complete: true,
    view: { calm: false },
  };
  return (notes ? { ...base, investigator_notes: notes } : base) as unknown as RunResult;
}

const note = { key: "i-0aa1", region_code: "OB", text: "Created on 2026-11-02 <b>by</b> j.marsh.", model: "m", at: "2026-11-05T02:30:00+00:00" };

describe("the investigator's note", () => {
  it("is labelled and sits under its own finding only", () => {
    const html = findings(run({ ok: true, detail: "", rows: [note] }), null, null);
    expect(html.match(/class="row-note"/g)).toHaveLength(1);
    expect(html).toContain(NOTE_LABEL);
    expect(NOTE_LABEL).toBe("Investigator's note, checked against the evidence");
    expect(html.indexOf("row-note")).toBeGreaterThan(html.indexOf("i-0aa1"));
    expect(html.indexOf("row-note")).toBeLessThan(html.indexOf("i-0bb2"));
  });

  it("is written as text, never as markup", () => {
    const html = findings(run({ ok: true, detail: "", rows: [note] }), null, null);
    expect(html).toContain("&lt;b&gt;by&lt;/b&gt;");
    expect(html).not.toContain("<b>by</b>");
  });

  it("is not shown when its chain does not verify", () => {
    const html = findings(run({ ok: false, detail: "note 0: hash mismatch", rows: [] }), null, null);
    expect(html).not.toContain("row-note");
    expect(html).not.toContain("hash mismatch");
  });

  it("leaves a finding without a note exactly as it renders in a run with no notes at all", () => {
    const withNotes = findings(run({ ok: true, detail: "", rows: [{ ...note, key: "other" }] }), null, null);
    expect(withNotes).toBe(findings(run(), null, null));
  });
});
