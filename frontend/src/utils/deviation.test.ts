import { describe, expect, it } from "vitest";
import { getDeviation } from "./deviation";

describe("getDeviation", () => {
  it("gibt null zurück wenn baseline null ist", () => {
    expect(getDeviation(null, 100)).toBeNull();
  });

  it("gibt null zurück wenn actual null ist", () => {
    expect(getDeviation(100, null)).toBeNull();
  });

  it("gibt null zurück wenn baseline 0 ist", () => {
    expect(getDeviation(0, 100)).toBeNull();
  });

  it("level 'over' wenn actual > 110% von baseline", () => {
    const r = getDeviation(100, 111);
    expect(r?.level).toBe("over");
  });

  it("level 'warn' wenn actual zwischen 100% und 110% von baseline", () => {
    const r = getDeviation(100, 105);
    expect(r?.level).toBe("warn");
  });

  it("level 'ok' wenn actual zwischen 95% und 100% von baseline", () => {
    const r = getDeviation(100, 97);
    expect(r?.level).toBe("ok");
  });

  it("level 'under' wenn actual unter 95% von baseline", () => {
    const r = getDeviation(100, 90);
    expect(r?.level).toBe("under");
  });

  it("level 'ok' genau bei 100%", () => {
    const r = getDeviation(100, 100);
    expect(r?.level).toBe("ok");
  });

  it("level 'over' genau bei 110.1%", () => {
    const r = getDeviation(100, 110.1);
    expect(r?.level).toBe("over");
  });

  it("level 'warn' genau bei 110%", () => {
    const r = getDeviation(100, 110);
    expect(r?.level).toBe("warn");
  });

  it("level 'ok' genau bei 95%", () => {
    const r = getDeviation(100, 95);
    expect(r?.level).toBe("ok");
  });

  it("level 'under' knapp unter 95%", () => {
    const r = getDeviation(100, 94.9);
    expect(r?.level).toBe("under");
  });

  it("berechnet ratio korrekt", () => {
    const r = getDeviation(200, 300);
    expect(r?.ratio).toBeCloseTo(1.5);
    expect(r?.overPct).toBeCloseTo(50);
  });

  it("funktioniert mit realen CHF-Beträgen (11% überschritten → over)", () => {
    const r = getDeviation(238275, 265000);
    expect(r?.level).toBe("over");
  });
});
