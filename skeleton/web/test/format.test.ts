import { describe, expect, it } from "vitest";
import { dateText, esc, isNegative, isZero, moneyText, stampText } from "../src/format";
import fixture from "./fixture";

describe("moneyText matches Python money_text on the API's decimal strings", () => {
  it.each(fixture.money.map((m) => [m.amount, m.text] as const))("%s", (amount, text) => {
    expect(moneyText(amount)).toBe(text);
  });

  it("knows the sign and zero without a float", () => {
    expect(isNegative("-0.0000000001")).toBe(true);
    expect(isNegative("-0")).toBe(false);
    expect(isZero("0E-12")).toBe(true);
    expect(isZero("1E-30")).toBe(false);
  });
});

describe("escaping and dates", () => {
  it("escapes the five HTML characters", () => {
    expect(esc(`<a href="x" onclick='y'>&</a>`)).toBe("&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;&lt;/a&gt;");
  });

  it("writes dates in UTC", () => {
    expect(dateText("2026-11-04T23:30:00-05:00")).toBe("05 Nov 2026");
    expect(stampText("2026-11-06T02:00:00+00:00")).toBe("02:00 UTC · 06 Nov 2026");
  });
});
