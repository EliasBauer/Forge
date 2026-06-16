import { describe, expect, it } from "vitest";
import { chf, pct, signedPct } from "./format";

// format.ts verwendet typografische Sonderzeichen (explizit als \u-Escapes):
const NBSP  = " "; // Non-Breaking Space        — nach "CHF", vor "%"
const NNBSP = " "; // Narrow No-Break Space     — nach Minuszeichen
const MINUS = "−"; // Minus Sign                — negative Beträge
const DASH  = "–"; // En Dash                  — Platzhalterwert null/undefined

describe("chf", () => {
  it("formatiert positive Beträge mit Tausendertrennzeichen", () => {
    expect(chf(1234567.89)).toBe(`CHF${NBSP}1'234'567.89`);
  });

  it("formatiert negative Beträge mit Minuszeichen", () => {
    expect(chf(-1500)).toBe(`CHF${NBSP}${MINUS}${NNBSP}1'500.00`);
  });

  it("gibt – zurück bei null", () => {
    expect(chf(null)).toBe(DASH);
  });

  it("gibt – zurück bei undefined", () => {
    expect(chf(undefined)).toBe(DASH);
  });

  it("akzeptiert GQLMeasurement-Objekt", () => {
    expect(chf({ value: 9500, unit: "CHF" })).toBe(`CHF${NBSP}9'500.00`);
  });

  it("lässt Währungspräfix weg bei withCurrency: false", () => {
    expect(chf(1000, { withCurrency: false })).toBe("1'000.00");
  });

  it("formatiert Null korrekt", () => {
    expect(chf(0)).toBe(`CHF${NBSP}0.00`);
  });

  it("rundet auf 2 Dezimalstellen", () => {
    expect(chf(99.999)).toBe(`CHF${NBSP}100.00`);
  });
});

describe("pct", () => {
  it("formatiert Prozentwert mit einer Dezimalstelle", () => {
    expect(pct(65.17)).toBe(`65.2${NBSP}%`);
  });

  it("gibt – zurück bei null", () => {
    expect(pct(null)).toBe(DASH);
  });

  it("gibt – zurück bei undefined", () => {
    expect(pct(undefined)).toBe(DASH);
  });

  it("formatiert 0 korrekt", () => {
    expect(pct(0)).toBe(`0.0${NBSP}%`);
  });

  it("formatiert 100 korrekt", () => {
    expect(pct(100)).toBe(`100.0${NBSP}%`);
  });
});

describe("signedPct", () => {
  it("gibt – und grau zurück bei null", () => {
    const r = signedPct(null);
    expect(r.text).toBe(DASH);
    expect(r.colorClass).toBe("text-gray-400");
  });

  it("positiver Wert ist grün bei neg-bad (default)", () => {
    const r = signedPct(5.3);
    expect(r.text).toBe(`+5.3${NBSP}%`);
    expect(r.colorClass).toBe("text-emerald-700");
  });

  it("negativer Wert ist rot bei neg-bad (default)", () => {
    const r = signedPct(-12.5);
    expect(r.text).toBe(`${MINUS}12.5${NBSP}%`);
    expect(r.colorClass).toBe("text-rose-700");
  });

  it("negativer Wert ist grün bei pos-bad", () => {
    const r = signedPct(-3.0, "pos-bad");
    expect(r.text).toBe(`${MINUS}3.0${NBSP}%`);
    expect(r.colorClass).toBe("text-emerald-700");
  });

  it("positiver Wert ist rot bei pos-bad", () => {
    const r = signedPct(8.0, "pos-bad");
    expect(r.text).toBe(`+8.0${NBSP}%`);
    expect(r.colorClass).toBe("text-rose-700");
  });

  it("0 ergibt grau und korrekten Text", () => {
    const r = signedPct(0);
    expect(r.colorClass).toBe("text-gray-700");
    expect(r.text).toBe(`0.0${NBSP}%`);
  });
});
