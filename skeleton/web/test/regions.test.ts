// A region reads by its plain label first. A night stored without labels gets them from its view, which the API builds
// from the app's current control; the Halloween name stays as the small tag.
import { describe, expect, it } from "vitest";
import { regionLabel, regionNamed } from "../src/regions";
import type { RunResult } from "../src/types";
import fixture from "./fixture";

const served = fixture.pack.relabelled.displayed[0].document as unknown as RunResult;

describe("a night stored without region labels", () => {
  it("takes its plain labels from the view the API built", () => {
    expect(served.region_labels).toEqual({});
    expect(regionLabel(served, "OB")).toBe("Running and billed, never approved");
    expect(regionLabel(served, "O")).toBe("Exists, never approved, free");
    expect(regionLabel(served, "I")).toBe("Approved, but gone");
  });

  it("keeps the Halloween name as the small tag beside the label", () => {
    const named = regionNamed(served, "OB");
    expect(named).toContain('<span class="region-label">Running and billed, never approved</span>');
    expect(named).toContain('<span class="region-tag-name">Vampire</span>');
  });

  it("falls back to the built-in plain label when the view has none", () => {
    const bare = { ...served, view: { ...served.view, region_labels: undefined } } as RunResult;
    expect(regionLabel(bare, "OB")).toBe("Exists and billed, never approved");
  });
});
