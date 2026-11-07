import { describe, expect, it } from "vitest";
import { changeOneByte, verifyPack } from "../src/verify";
import fixture from "./fixture";

const manifest = fixture.pack.manifest;

describe("browser verification gives Python's verdict on a hostile pack", () => {
  it.each(fixture.pack.variants.map((v) => [v.name, v] as const))("%s", async (_name, variant) => {
    const result = await verifyPack(variant.jsonl, manifest);
    expect(result.ok).toBe(variant.verdict.ok);
    expect(result.failedRow).toBe(variant.verdict.failed_row);
    expect(result.detail).toBe(variant.verdict.detail);
    if (variant.verdict.ok) {
      expect(result.rows).toBe(variant.verdict.rows);
      expect(result.findings).toBe(variant.verdict.findings);
      expect(result.finalHash).toBe(variant.verdict.final_hash);
      expect(result.finalHash).toBe(manifest.final_chain_hash);
    }
  });

  it("gives Python's verdict on a pack written before the header row, and says it has none", async () => {
    const { jsonl, manifest: legacyManifest, verdict } = fixture.pack.legacy;
    const result = await verifyPack(jsonl, legacyManifest);
    expect(result.ok).toBe(true);
    expect(result.hasHeader).toBe(false);
    expect(result.detail).toBe(verdict.detail);
    expect(result.detail).toContain("carries no header row");
  });

  it("fails when the manifest names another run than the chain header does", async () => {
    const untouched = fixture.pack.variants[0].jsonl;
    const result = await verifyPack(untouched, { ...manifest, run_id: "0123456789abcdef" });
    expect(result.ok).toBe(false);
    expect(result.detail).toMatch(/^manifest run_id differs from the chain header/);
  });

  it("reports every row as it is checked", async () => {
    const untouched = fixture.pack.variants[0].jsonl;
    const seen: number[] = [];
    await verifyPack(untouched, manifest, (row) => {
      seen.push(row.index);
    });
    expect(seen).toEqual([...Array(fixture.pack.variants[0].verdict.rows).keys()]);
  });

  it("changes one byte exactly as the Python fixture does", () => {
    const untouched = fixture.pack.variants[0].jsonl;
    const changed = changeOneByte(untouched);
    expect(changed?.text).toBe(fixture.pack.variants.find((v) => v.name === "change one byte")?.jsonl);
    expect(changed?.before).not.toBe(changed?.after);
  });
});

describe("the page against the chain gives Python's verdict", () => {
  const untouched = fixture.pack.variants[0].jsonl;

  it.each(fixture.pack.displayed.map((d) => [d.name, d] as const))("%s", async (_name, shown) => {
    const result = await verifyPack(untouched, manifest, undefined, shown.document);
    expect(result.ok).toBe(shown.verdict.ok);
    expect(result.detail).toBe(shown.verdict.detail);
    expect(result.failedRow).toBe(shown.verdict.failed_row);
    if (shown.verdict.ok) expect(result.finalHash).toBe(shown.verdict.final_hash);
  });

  it("fails on a forged finding and names it", async () => {
    const forged = fixture.pack.displayed.find((d) => d.name === "a forged finding");
    const result = await verifyPack(untouched, manifest, undefined, forged?.document);
    expect(result.ok).toBe(false);
    expect(result.detail).toContain("is shown but is not in the evidence");
  });

  it("fails on a page that says incomplete to hide the bill, its findings still shown", async () => {
    const served = fixture.pack.displayed.find((d) => d.name === "served as it is")?.document;
    const page = JSON.parse(JSON.stringify(served)) as Record<string, unknown>;
    const view = page.view as Record<string, unknown>;
    page.complete = false;
    page.billed_total = page.billed_unkeyed = "0";
    view.billed_total = view.unkeyed_total = view.keyed_total = "0";
    expect((page.findings as unknown[]).length).toBeGreaterThan(0);
    const result = await verifyPack(untouched, manifest, undefined, page);
    expect(result.ok).toBe(false);
    expect(result.detail).toContain("complete: the page shows false, the evidence has true");
  });

  it.each(fixture.pack.completeness.map((c) => [c.name, c] as const))("%s", async (_name, c) => {
    const result = await verifyPack(c.jsonl, c.manifest, undefined, c.document);
    expect(result.ok).toBe(c.verdict.ok);
    expect(result.detail).toBe(c.verdict.detail);
  });
});

describe("the manifest names exactly the three ledgers, as in Python", () => {
  it.each(fixture.pack.ledgers.map((c) => [c.name, c] as const))("%s", async (_name, c) => {
    const result = await verifyPack(c.jsonl, c.manifest);
    expect(result.ok).toBe(false);
    expect(result.detail).toBe(c.verdict.detail);
    expect(result.failedRow).toBe(c.verdict.failed_row);
  });
});

describe("every number in the headline is checked, as in Python", () => {
  const untouched = fixture.pack.variants[0].jsonl;
  const named = (name: string) => fixture.pack.displayed.find((d) => d.name === name);

  it("refuses a headline amount written without a dollar sign", async () => {
    const shown = named("a headline amount written without a dollar sign");
    const result = await verifyPack(untouched, manifest, undefined, shown?.document);
    expect(result.ok).toBe(false);
    expect(result.detail).toContain("which is not one of the headline's counts or amounts");
  });

  it("reads a minus after a letter as joining two words, like the explanation guard", async () => {
    const shown = named("a headline number after a letter and a minus");
    const result = await verifyPack(untouched, manifest, undefined, shown?.document);
    expect(result.detail).toContain("the number 7,");
    expect(result.detail).not.toContain("the number -7");
  });
});

describe("a night stored without labels, its headline rebuilt in plain words, is checked as in Python", () => {
  const { jsonl, manifest: labManifest, displayed } = fixture.pack.relabelled;

  it.each(displayed.map((d) => [d.name, d] as const))("%s", async (_name, shown) => {
    const result = await verifyPack(jsonl, labManifest, undefined, shown.document);
    expect(result.ok).toBe(shown.verdict.ok);
    expect(result.detail).toBe(shown.verdict.detail);
    expect(result.failedRow).toBe(shown.verdict.failed_row);
  });

  it("shows the lab night's own figures in plain words", () => {
    const view = displayed[0].document.view as { headline_sentences: string[] };
    expect(view.headline_sentences).toEqual([
      "3 resources are running and on the bill with no approval: $0.7172 so far.",
      "2 resources exist with no approval and cost nothing.",
      "1 approved resource is gone.",
    ]);
  });

  it("fails on every edit of a count or an amount in the rebuilt headline", async () => {
    const edits = displayed.slice(1);
    expect(edits.length).toBe(4);
    for (const shown of edits) {
      const result = await verifyPack(jsonl, labManifest, undefined, shown.document);
      expect(result.ok, shown.name).toBe(false);
      expect(result.detail, shown.name).toContain("headline: the page shows");
    }
  });
});

