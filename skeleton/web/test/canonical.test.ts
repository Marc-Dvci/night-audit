import { describe, expect, it } from "vitest";
import { byCodePoint, canonical, pyString } from "../src/canonical";
import fixture from "./fixture";

describe("canonical JSON matches Python json.dumps(sort_keys, compact, ensure_ascii)", () => {
  it.each(fixture.canonical.map((c, i) => [i, c] as const))("case %i", (_i, c) => {
    expect(canonical(c.value)).toBe(c.canonical);
  });

  it("sorts keys by code point, not by UTF-16 unit", () => {
    // U+FFFF is one unit 0xFFFF; U+10000 is the pair 0xD800 0xDC00. By UTF-16 units the pair sorts first.
    expect(["\u{10000}", "\uffff"].sort()).toEqual(["\u{10000}", "\uffff"]);
    expect(["\u{10000}", "\uffff"].sort(byCodePoint)).toEqual(["\uffff", "\u{10000}"]);
    expect(canonical({ "\u{10000}": 1, "\uffff": 2 })).toBe('{"\\uffff":2,"\\ud800\\udc00":1}');
  });

  it("escapes DEL, bidi overrides and lone surrogates the way Python does", () => {
    expect(pyString("\x7f")).toBe('"\\u007f"');
    expect(pyString("\u202e")).toBe('"\\u202e"');
    expect(pyString("\ud800")).toBe('"\\ud800"');
    expect(pyString('"\\/\n')).toBe('"\\"\\\\/\\n"');
  });
});
