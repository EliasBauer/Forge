import { chf } from "../utils/format";
import { getProjektStatus } from "../utils/projektStatus";

type Props = {
  planWV: number | null;
  sollWV: number | null;
  ist: number;
  ak: number;
};

export default function ProjektStatusMini({ planWV, sollWV, ist, ak }: Props) {
  const status = getProjektStatus({ planWV, sollWV, ist, ak });
  if (!status) {
    return <span className="text-[12px] italic text-gray-400">keine WV-Summe</span>;
  }

  // Der Mini-Balken skaliert immer auf Plan-WV; ein Ist darüber sitzt am Rand.
  const akBreite = (status.akPct / status.planPct) * 100;
  const istPosition = Math.min((status.istPct / status.planPct) * 100, 100);

  return (
    <div className="flex items-center gap-2.5">
      <span className="relative w-[110px] h-1.5 rounded-full shrink-0 bg-gray-100">
        <span
          className="absolute inset-0 rounded-full"
          style={{ backgroundColor: "var(--forge-blue-light)" }}
        />
        <span
          className="absolute top-0 bottom-0 left-0 rounded-full"
          style={{ width: `${akBreite}%`, backgroundColor: "var(--forge-green)" }}
        />
        <span
          className="absolute top-[-2px] bottom-[-2px]"
          style={{
            left: `calc(${istPosition}% - ${status.istOverPlan ? "4px" : "1px"})`,
            width: status.istOverPlan ? "4px" : "2px",
            backgroundColor: "var(--forge-red)",
          }}
        />
      </span>
      <span
        data-testid="mini-text"
        className={`text-[12px] tabular-nums whitespace-nowrap ${
          status.istOverPlan ? "text-rose-700 font-medium" : "text-gray-600"
        }`}
      >
        <span className="font-medium text-inherit">
          {chf(status.offen, { withCurrency: false }).replace(".00", "")}
        </span>{" "}
        offen · {status.offenPct.toFixed(0)} %{status.istOverPlan ? " ⚠" : ""}
      </span>
    </div>
  );
}
