export type GQLMeasurement = { value: number; unit: string };

function formatAbsCHF(n: number): string {
  const abs = Math.abs(n);
  const [intPart, decPart] = abs.toFixed(2).split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, "'");
  return `${grouped}.${decPart}`;
}

export function chf(
  val: GQLMeasurement | number | null | undefined,
  opts: { withCurrency?: boolean } = {},
): string {
  const { withCurrency = true } = opts;
  if (val == null) return "–";
  const num = typeof val === "number" ? val : val.value;
  const sign = num < 0 ? "− " : "";
  const formatted = `${sign}${formatAbsCHF(num)}`;
  return withCurrency ? `CHF ${formatted}` : formatted;
}

export function pct(val: number | null | undefined): string {
  if (val == null) return "–";
  return `${val.toFixed(1)} %`;
}

export function signedPct(
  val: number | null | undefined,
  polarity: "neg-bad" | "pos-bad" = "neg-bad",
): { text: string; colorClass: string } {
  if (val == null) return { text: "–", colorClass: "text-gray-400" };
  const isNeg = val < 0;
  const isGood = polarity === "neg-bad" ? !isNeg : isNeg;
  const colorClass = val === 0 ? "text-gray-700" : isGood ? "text-emerald-700" : "text-rose-700";
  const sign = val < 0 ? "−" : "+";
  const text = val === 0 ? `0.0 %` : `${sign}${Math.abs(val).toFixed(1)} %`;
  return { text, colorClass };
}
