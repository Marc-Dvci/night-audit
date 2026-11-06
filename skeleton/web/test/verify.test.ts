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
