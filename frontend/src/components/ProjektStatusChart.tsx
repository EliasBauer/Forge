import { chf } from "../utils/format";
import { getProjektStatus, type Segment } from "../utils/projektStatus";

type Props = {
  planWV: number | null;
  sollWV: number | null;
  ist: number;
  ak: number;
};

const GESTRICHELT_ROT =
  "repeating-linear-gradient(90deg, var(--forge-red) 0 6px, transparent 6px 10px)";
const GESTRICHELT_HELLBLAU =
  "repeating-linear-gradient(90deg, var(--forge-blue-light) 0 6px, transparent 6px 10px)";

function Seg({
  seg,
  style,
}: {
  seg: Segment | null;
  style: React.CSSProperties;
}) {
  if (!seg) return null;
  return (
    <div
      className="absolute top-0 h-full"
      style={{ left: `${seg.from}%`, width: `${seg.to - seg.from}%`, ...style }}
    />
  );
}

function LegendItem({ label, style }: { label: string; style: React.CSSProperties }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-3.5 h-2 rounded-sm shrink-0" style={style} />
      {label}
    </span>
  );
}

function Row({
  label,
  value,
  children,
}: {
  label: string;
  value: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className="grid items-center gap-3"
      style={{ gridTemplateColumns: "120px 1fr 150px" }}
    >
      <span className="text-[10px] uppercase tracking-wider font-semibold text-gray-500">
        {label}
      </span>
      <div className="relative h-2.5 rounded-sm bg-gray-100">{children}</div>
      <span className="text-right text-[12px] tabular-nums">{value}</span>
    </div>
  );
}

export default function ProjektStatusChart({ planWV, sollWV, ist, ak }: Props) {
  const status = getProjektStatus({ planWV, sollWV, ist, ak });

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm mt-5">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-[15px] font-semibold text-gray-900">
          Projektstatus auf einen Blick
        </h2>
        {status && (
          <div className="flex items-center gap-3 text-[11px] text-gray-500 flex-wrap">
            <LegendItem
              label="Soll-WV"
              style={{ backgroundColor: "var(--forge-blue-light)" }}
            />
            <LegendItem
              label="Auffüllung bis Plan-WV"
              style={{ backgroundColor: "var(--forge-blue)" }}
            />
            <LegendItem
              label="Ist-Kosten kum."
              style={{ backgroundColor: "var(--forge-red)" }}
            />
            <LegendItem
              label="AK verrechnet"
              style={{ backgroundColor: "var(--forge-green)" }}
            />
            <LegendItem label="Überschreitung Plan-WV" style={{ background: GESTRICHELT_ROT }} />
          </div>
        )}
      </div>

      {!status ? (
        <p className="px-6 py-4 text-[13px] italic text-gray-500">
          Keine WV-Summe erfasst — Plan-WV fehlt.
        </p>
      ) : (
        <div
          className="px-6 py-4 grid gap-6 items-center"
          style={{ gridTemplateColumns: "minmax(0, 1fr) 200px" }}
        >
          <div className="flex flex-col gap-3">
            <Row
              label="Plan-WV"
              value={
                <span className="font-semibold text-gray-900">{chf(planWV)}</span>
              }
            >
              <Seg
                seg={status.sollLight}
                style={{
                  backgroundColor: "var(--forge-blue-light)",
                  borderRadius: "3px 0 0 3px",
                }}
              />
              <Seg seg={status.fillDark} style={{ backgroundColor: "var(--forge-blue)" }} />
              <Seg seg={status.sollGhost} style={{ background: GESTRICHELT_HELLBLAU }} />
              <Seg seg={status.overrun} style={{ background: GESTRICHELT_ROT }} />
            </Row>

            <Row
              label="Ist-Kosten kum."
              value={
                <span
                  data-testid="ist-wert"
                  className={status.istOverPlan ? "text-rose-700 font-semibold" : "text-gray-700"}
                >
                  {status.istOverPlan ? "⚠ " : ""}
                  {chf(ist)}
                </span>
              }
            >
              <div
                className="absolute top-0 h-full rounded-sm"
                style={{ width: `${status.istPct}%`, backgroundColor: "var(--forge-red)" }}
              />
              <div
                className="absolute top-[-3px] bottom-[-3px] w-px"
                style={{ left: `${status.planPct}%`, backgroundColor: "var(--forge-blue)" }}
              />
            </Row>

            <Row
              label="AK verrechnet"
              value={
                <span className={ak === 0 ? "text-gray-400" : "text-gray-700"}>
                  {chf(ak)}
                  {status.akCapped && (
                    <span className="ml-1 text-[10px] text-gray-500">gedeckelt</span>
                  )}
                </span>
              }
            >
              <div
                className="absolute top-0 h-full rounded-sm"
                style={{ width: `${status.akPct}%`, backgroundColor: "var(--forge-green)" }}
              />
              <div
                className="absolute top-[-3px] bottom-[-3px] w-px"
                style={{ left: `${status.planPct}%`, backgroundColor: "var(--forge-blue)" }}
              />
            </Row>
          </div>

          <div className="border-l-2 border-gray-200 pl-4">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-gray-500">
              Offen (Plan-WV − AK)
            </div>
            <div className="text-xl font-semibold text-gray-900 tabular-nums">
              {chf(status.offen)}
            </div>
            <div className="text-[12px] text-gray-500 tabular-nums">
              {status.offenPct.toFixed(1)} % von Plan-WV
            </div>
            {status.istOverPlan && (
              <div className="mt-1 text-[11px] text-rose-700 tabular-nums">
                Ist über Plan-WV: +{chf(status.istOverPlanAbs)} (+
                {status.istOverPlanPct.toFixed(1)} %)
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
