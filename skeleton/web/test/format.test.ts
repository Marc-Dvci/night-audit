import { describe, expect, it } from "vitest";
import { dateText, esc, headlineMoneyText, isNegative, isZero, moneyText, stampText } from "../src/format";
import fixture from "./fixture";

describe("moneyText matches Python money_text on the API's decimal strings", () => {
  it.each(fixture.money.map((m) => [m.amount, m.text] as const))("%s", (amount, text) => {
    expect(moneyText(amount)).toBe(text);
  });

  it.each(fixture.money.map((m) => [m.amount, m.headline] as const))("headline %s", (amount, text) => {
    expect(headlineMoneyText(amount)).toBe(text);
  });

  it("rounds the headline half-even to four figures: 0.71725 is $0.7172, 0.71735 is $0.7174", () => {
    expect(headlineMoneyText("0.7172358001")).toBe("$0.7172");
    expect(headlineMoneyText("0.71725")).toBe("$0.7172");
    expect(headlineMoneyText("0.71735")).toBe("$0.7174");
    expect(headlineMoneyText("0.71725000001")).toBe("$0.7173");
    expect(headlineMoneyText("123.456")).toBe("$123.46");
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
