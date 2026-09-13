import { describe, expect, it } from "vitest";
import { getProjektStatus } from "./projektStatus";

describe("getProjektStatus", () => {
  it("gibt null ohne Plan-WV", () => {
    expect(getProjektStatus({ planWV: null, sollWV: null, ist: 100, ak: 0 })).toBeNull();
  });

  it("gibt null bei Plan-WV 0", () => {
    expect(getProjektStatus({ planWV: 0, sollWV: 0, ist: 100, ak: 0 })).toBeNull();
  });

  it("Normalfall: hellblau bis Soll, dunkelblau bis Plan", () => {
    const r = getProjektStatus({ planWV: 250000, sollWV: 230000, ist: 168400, ak: 120000 })!;
    expect(r.scale).toBe(250000);
    expect(r.sollLight).toEqual({ from: 0, to: 92 });
    expect(r.fillDark).toEqual({ from: 92, to: 100 });
    expect(r.sollGhost).toBeNull();
    expect(r.overrun).toBeNull();
    expect(r.offen).toBe(130000);
    expect(r.offenPct).toBeCloseTo(52, 5);
    expect(r.istOverPlan).toBe(false);
  });

  it("Soll gleich Plan: alles hellblau, keine Auffüllung", () => {
    const r = getProjektStatus({ planWV: 250000, sollWV: 250000, ist: 168400, ak: 0 })!;
    expect(r.sollLight).toEqual({ from: 0, to: 100 });
    expect(r.fillDark).toBeNull();
    expect(r.offen).toBe(250000);
    expect(r.offenPct).toBe(100);
  });

  it("Ist über Plan: Massstab waechst, Ueberschreitung als eigenes Segment", () => {
    const r = getProjektStatus({ planWV: 250000, sollWV: 230000, ist: 290000, ak: 120000 })!;
    expect(r.scale).toBe(290000);
    expect(r.istPct).toBe(100);
    expect(r.planPct).toBeCloseTo(86.2069, 3);
    expect(r.overrun!.from).toBeCloseTo(86.2069, 3);
    expect(r.overrun!.to).toBe(100);
    expect(r.istOverPlan).toBe(true);
    expect(r.istOverPlanAbs).toBe(40000);
    expect(r.istOverPlanPct).toBeCloseTo(16, 5);
  });

  it("AK groesser als Plan wird gedeckelt", () => {
    const r = getProjektStatus({ planWV: 250000, sollWV: 250000, ist: 168400, ak: 260000 })!;
    expect(r.akCapped).toBe(true);
    expect(r.akPct).toBe(100);
    expect(r.offen).toBe(0);
    expect(r.offenPct).toBe(0);
  });

  it("Plan kleiner als Soll: dunkelblau bis Plan, Ueberhang gestrichelt", () => {
    const r = getProjektStatus({ planWV: 220000, sollWV: 250000, ist: 168400, ak: 120000 })!;
    expect(r.scale).toBe(250000);
    expect(r.sollLight).toBeNull();
    expect(r.fillDark).toEqual({ from: 0, to: 88 });
    expect(r.sollGhost).toEqual({ from: 88, to: 100 });
    expect(r.offen).toBe(100000);
    expect(r.offenPct).toBeCloseTo(45.4545, 3);
  });

  it("ohne Soll-WV gilt Soll gleich Plan", () => {
    const r = getProjektStatus({ planWV: 100000, sollWV: null, ist: 0, ak: 0 })!;
    expect(r.sollLight).toEqual({ from: 0, to: 100 });
    expect(r.fillDark).toBeNull();
  });
});
