export type ProjektStatusInput = {
  /** Plan-WV in CHF; ohne ihn gibt es kein Chart. */
  planWV: number | null;
  /** Soll-WV in CHF; null => gleich Plan-WV. */
  sollWV: number | null;
  /** Kumulierte Ist-Kosten in CHF. */
  ist: number;
  /** Bisher verrechnete A-Konto-Zahlungen in CHF. */
  ak: number;
};

/** Balkenabschnitt in Prozent der Chart-Breite. */
export type Segment = { from: number; to: number };

export type ProjektStatusResult = {
  /** Bezugsgroesse der Balkenbreite: max(Plan, Soll, Ist). */
  scale: number;
  planPct: number;
  /** Hellblau: 0 bis Soll-WV (nur wenn Plan >= Soll). */
  sollLight: Segment | null;
  /** Dunkelblau: Auffuellung bis Plan-WV. */
  fillDark: Segment | null;
  /** Hellblau gestrichelt: Soll-Ueberhang (nur wenn Soll > Plan). */
  sollGhost: Segment | null;
  /** Rot gestrichelt: Plan bis Ist (nur wenn Ist > Plan). */
  overrun: Segment | null;
  istPct: number;
  istOverPlan: boolean;
  istOverPlanAbs: number;
  istOverPlanPct: number;
  /** AK-Balken, auf Plan-WV gedeckelt. */
  akPct: number;
  akCapped: boolean;
  offen: number;
  offenPct: number;
};

export function getProjektStatus(
  input: ProjektStatusInput,
): ProjektStatusResult | null {
  const { planWV, ist, ak } = input;
  if (planWV == null || planWV <= 0) return null;

  const sollWV = input.sollWV ?? planWV;
  const scale = Math.max(planWV, sollWV, ist);
  const toPct = (value: number): number => (value / scale) * 100;

  const planAbSoll = planWV >= sollWV;
  const sollLight =
    planAbSoll && sollWV > 0 ? { from: 0, to: toPct(sollWV) } : null;
  const fillDark = planAbSoll
    ? planWV > sollWV
      ? { from: toPct(sollWV), to: toPct(planWV) }
      : null
    : { from: 0, to: toPct(planWV) };
  const sollGhost = planAbSoll
    ? null
    : { from: toPct(planWV), to: toPct(sollWV) };

  const istOverPlan = ist > planWV;
  const akEffektiv = Math.min(ak, planWV);

  return {
    scale,
    planPct: toPct(planWV),
    sollLight,
    fillDark,
    sollGhost,
    overrun: istOverPlan ? { from: toPct(planWV), to: toPct(ist) } : null,
    istPct: toPct(ist),
    istOverPlan,
    istOverPlanAbs: istOverPlan ? ist - planWV : 0,
    istOverPlanPct: istOverPlan ? ((ist - planWV) / planWV) * 100 : 0,
    akPct: toPct(akEffektiv),
    akCapped: ak > planWV,
    offen: planWV - akEffektiv,
    offenPct: ((planWV - akEffektiv) / planWV) * 100,
  };
}
