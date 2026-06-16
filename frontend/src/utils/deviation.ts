export type DeviationLevel = "over" | "warn" | "ok" | "under";

export interface DeviationResult {
  ratio: number;
  overPct: number;
  level: DeviationLevel;
}

export function getDeviation(
  baseline: number | null | undefined,
  actual: number | null | undefined,
): DeviationResult | null {
  if (baseline == null || actual == null || baseline === 0) return null;
  const ratio = actual / baseline;
  const overPct = (ratio - 1) * 100;
  let level: DeviationLevel;
  if (ratio > 1.1) level = "over";
  else if (ratio > 1.0) level = "warn";
  else if (ratio >= 0.95) level = "ok";
  else level = "under";
  return { ratio, overPct, level };
}

export const DEV_STYLES = {
  over:  { dot: "bg-rose-500",    text: "text-rose-700",    bg: "bg-rose-50",    label: "Überschritten" },
  warn:  { dot: "bg-amber-500",   text: "text-amber-700",   bg: "bg-amber-50",   label: "Grenzbereich" },
  ok:    { dot: "bg-emerald-500", text: "text-emerald-700", bg: "bg-emerald-50", label: "Im Soll" },
  under: { dot: "bg-emerald-500", text: "text-emerald-700", bg: "bg-emerald-50", label: "Unter Soll" },
} as const;
