import { chf } from "../utils/format";
import { GESTRICHELT_ROT } from "../utils/chartStyles";
import { getDeviation, DEV_STYLES } from "../utils/deviation";

export type KategorieZeile = {
  schluessel: string;
  label: string;
  planWV: number | null;
  ist: number | null;
};

function LegendItem({ label, style }: { label: string; style: React.CSSProperties }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-3.5 h-2 rounded-sm shrink-0" style={style} />
      {label}
    </span>
  );
}

export default function ProjektKategorienChart({ rows }: { rows: KategorieZeile[] }) {
  const visible = rows.filter((r) => r.planWV != null || r.ist != null);
  if (visible.length === 0) return null;

  // Eine gemeinsame Bezugsgrösse für alle Zeilen — nur so sagt die Balkenlänge
  // etwas über das Gewicht einer Kategorie im Projekt aus.
  const skala = Math.max(...visible.flatMap((r) => [r.planWV ?? 0, r.ist ?? 0]), 1);
  const pctVon = (wert: number): number => (wert / skala) * 100;

  const deviations = visible.map((r) => getDeviation(r.planWV, r.ist));
  const countOver = deviations.filter((d) => d?.level === "over").length;
  const countWarn = deviations.filter((d) => d?.level === "warn").length;
  const countOk = deviations.filter(
    (d) => d != null && (d.level === "ok" || d.level === "under"),
  ).length;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm mt-5">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-[15px] font-semibold text-gray-900">
          Projektkategorien auf einen Blick
        </h2>
        <div className="flex items-center gap-4 text-[11px] font-medium">
          {countOver > 0 && (
            <span className="inline-flex items-center gap-1.5 text-rose-700">
              <span className="w-2 h-2 rounded-full bg-rose-500" />
              {countOver} überschritten
            </span>
          )}
          {countWarn > 0 && (
            <span className="inline-flex items-center gap-1.5 text-amber-700">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              {countWarn} Grenzbereich
            </span>
          )}
          {countOk > 0 && (
            <span className="inline-flex items-center gap-1.5 text-emerald-700">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              {countOk} im Soll
            </span>
          )}
        </div>
      </div>

      <div className="px-6 py-4">
        <div className="flex items-center gap-3 text-[11px] text-gray-500 flex-wrap mb-4">
          <LegendItem label="Plan-WV" style={{ backgroundColor: "var(--forge-blue-light)" }} />
          <LegendItem
            label="Ist-Kosten"
            style={{ backgroundColor: "var(--forge-red)", width: "2px" }}
          />
          <LegendItem label="Überschreitung Plan-WV" style={{ background: GESTRICHELT_ROT }} />
        </div>

        <div className="flex flex-col gap-3">
          {visible.map((row, i) => {
            const dev = deviations[i];
            const level = dev?.level ?? null;
            const planPct = row.planWV != null ? pctVon(row.planWV) : 0;
            const istPct = row.ist != null ? pctVon(row.ist) : 0;
            const ueberschritten =
              row.planWV != null && row.ist != null && row.ist > row.planWV;

            return (
              <div
                key={row.schluessel}
                className="grid items-center gap-4 py-2 border-b border-gray-50 last:border-0"
                style={{ gridTemplateColumns: "180px 1fr 150px" }}
              >
                {/* Label mit Status-Punkt, darunter der Plan-WV-Betrag */}
                <div className="min-w-0">
                  <span className="flex items-center gap-2 min-w-0">
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        level ? DEV_STYLES[level].dot : "bg-gray-200"
                      }`}
                    />
                    <span className="text-sm text-gray-700 truncate">{row.label}</span>
                  </span>
                  <span className="block text-[10px] text-gray-400 tabular-nums pl-3.5">
                    Plan-WV {chf(row.planWV)}
                  </span>
                </div>

                {/* Ein Balken: hellblau bis Plan-WV, gestrichelt rot darüber
                    hinaus, rote Linie an der Ist-Position. */}
                <div className="relative h-2.5 rounded-sm bg-gray-100">
                  <div
                    data-testid={`kat-plan-${row.schluessel}`}
                    className="absolute top-0 h-full rounded-sm"
                    style={{
                      left: 0,
                      width: `${planPct}%`,
                      backgroundColor: "var(--forge-blue-light)",
                    }}
                  />
                  {ueberschritten && (
                    <div
                      data-testid={`kat-overrun-${row.schluessel}`}
                      className="absolute top-0 h-full"
                      style={{
                        left: `${planPct}%`,
                        width: `${istPct - planPct}%`,
                        background: GESTRICHELT_ROT,
                      }}
                    />
                  )}
                  {row.ist != null && (
                    <div
                      data-testid={`kat-ist-${row.schluessel}`}
                      className="absolute top-[-3px] bottom-[-3px] w-px"
                      style={{ left: `${istPct}%`, backgroundColor: "var(--forge-red)" }}
                    />
                  )}
                </div>

                {/* Ist-Betrag und Abweichung */}
                <div className="text-right">
                  <span
                    className={`block text-[12px] tabular-nums ${
                      level ? DEV_STYLES[level].text : "text-gray-400"
                    }`}
                  >
                    {chf(row.ist)}
                  </span>
                  {dev != null ? (
                    <span
                      className={`inline-flex items-center gap-1 text-[11px] font-medium tabular-nums ${
                        DEV_STYLES[dev.level].text
                      }`}
                    >
                      {(dev.level === "over" || dev.level === "warn") && (
                        <span className="text-[10px]">⚠</span>
                      )}
                      {dev.overPct >= 0 ? "+" : "−"}
                      {Math.abs(dev.overPct).toFixed(1)} %
                    </span>
                  ) : row.ist != null ? (
                    // getDeviation() braucht eine Basis > 0. Ist-Kosten ohne
                    // Plan-WV haben keine Abweichung, sind aber das Gegenteil
                    // von „noch offen" — sie brauchen einen eigenen Hinweis.
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-700">
                      <span className="text-[10px]">⚠</span>
                      ohne Plan-WV
                    </span>
                  ) : row.planWV != null && row.planWV > 0 ? (
                    <span className="text-[11px] italic text-gray-400">noch offen</span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
