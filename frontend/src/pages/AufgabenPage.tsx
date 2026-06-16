import { useQuery } from "@apollo/client/react";
import { CheckCircle2, ChevronRight, Clock } from "lucide-react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { GET_FEHLENDE_STUNDENSATZ_JAHRE } from "../graphql/queries";

type Tone = "amber" | "blue" | "rose";

const TONES: Record<
  Tone,
  {
    iconBg: string;
    iconText: string;
    badge: string;
    chipBg: string;
    chipBorder: string;
    chipText: string;
    accent: string;
    rowHover: string;
  }
> = {
  amber: {
    iconBg: "bg-amber-100",
    iconText: "text-amber-700",
    badge: "bg-amber-100 text-amber-700",
    chipBg: "bg-amber-50",
    chipBorder: "border-amber-300",
    chipText: "text-amber-700",
    accent: "text-amber-600",
    rowHover: "hover:bg-amber-50/50",
  },
  blue: {
    iconBg: "bg-blue-100",
    iconText: "text-blue-700",
    badge: "bg-blue-100 text-blue-700",
    chipBg: "bg-blue-50",
    chipBorder: "border-blue-300",
    chipText: "text-blue-700",
    accent: "text-blue-600",
    rowHover: "hover:bg-blue-50/50",
  },
  rose: {
    iconBg: "bg-rose-100",
    iconText: "text-rose-700",
    badge: "bg-rose-100 text-rose-700",
    chipBg: "bg-rose-50",
    chipBorder: "border-rose-300",
    chipText: "text-rose-700",
    accent: "text-rose-600",
    rowHover: "hover:bg-rose-50/50",
  },
};

interface TodoItem {
  id: string;
  label: string;
  title: string;
  sub: string;
  href: string;
  action: string;
}

interface TodoGroup {
  id: string;
  tone: Tone;
  icon: React.ElementType;
  title: string;
  description: string;
  items: TodoItem[];
}

type StundensatzJahreData = {
  aufgabenStundensatz: { fehlendeStundensatzJahre: number[] };
};

function countLabel(n: number): string {
  if (n === 0) return "Keine offenen Punkte";
  if (n === 1) return "1 offener Punkt";
  return `${n} offene Punkte`;
}

export default function AufgabenPage() {
  const { data, loading, error } = useQuery<StundensatzJahreData>(
    GET_FEHLENDE_STUNDENSATZ_JAHRE,
    { fetchPolicy: "network-only" },
  );

  const fehlendeJahre = data?.aufgabenStundensatz.fehlendeStundensatzJahre ?? [];

  const groups: TodoGroup[] =
    fehlendeJahre.length > 0
      ? [
          {
            id: "stundensaetze",
            tone: "amber",
            icon: Clock,
            title: "Fehlende Stundensätze",
            description: "Für diese Jahre ist noch kein Stundensatz hinterlegt.",
            items: fehlendeJahre.map((jahr) => ({
              id: String(jahr),
              label: String(jahr),
              title: `Jahr ${jahr}`,
              sub: "Noch kein Stundensatz erfasst",
              href: "/stundensaetze",
              action: "Stundensatz erfassen",
            })),
          },
        ]
      : [];

  const totalItems = groups.reduce((sum, g) => sum + g.items.length, 0);

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-[22px] font-semibold text-gray-900">Aufgaben</h1>
        <p className="text-sm text-gray-500 mt-1">{loading ? "…" : countLabel(totalItems)}</p>
      </div>

      {loading && <p className="text-sm text-gray-500">Lade…</p>}

      {error && (
        <p
          className="rounded-lg p-4 border text-sm mb-4"
          style={{
            color: "var(--forge-red)",
            borderColor: "var(--forge-red)",
            backgroundColor: "var(--forge-red-soft)",
          }}
        >
          Fehler: {error.message}
        </p>
      )}

      {!loading && !error && groups.length === 0 && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-10 flex flex-col items-center gap-3 max-w-2xl">
          <CheckCircle2 className="w-16 h-16 text-emerald-500" />
          <p className="text-[15px] font-semibold text-gray-900">Alles erledigt</p>
          <p className="text-sm text-gray-500 text-center">
            Aktuell sind keine offenen Punkte vorhanden. Neue Hinweise erscheinen hier automatisch.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-4 max-w-2xl">
        {groups.map((group) => {
          const t = TONES[group.tone];
          const Icon = group.icon;
          return (
            <div key={group.id} className="bg-white rounded-lg border border-gray-200 shadow-sm">
              <div className="flex items-start gap-3 px-5 py-4 border-b border-gray-100">
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${t.iconBg} ${t.iconText}`}
                >
                  <Icon size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[15px] font-semibold text-gray-900">{group.title}</span>
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full min-w-5 text-center ${t.badge}`}
                    >
                      {group.items.length}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-0.5">{group.description}</p>
                </div>
              </div>

              <ul>
                {group.items.map((item, idx) => (
                  <li
                    key={item.id}
                    className={idx < group.items.length - 1 ? "border-b border-gray-100" : ""}
                  >
                    <Link
                      to={item.href}
                      className={`flex items-center gap-4 px-5 py-3 group transition-colors ${t.rowHover}`}
                    >
                      <div
                        className={`w-9 h-9 rounded-md border flex items-center justify-center flex-shrink-0 text-sm font-semibold tabular-nums ${t.chipBg} ${t.chipBorder} ${t.chipText}`}
                      >
                        {item.label}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800">{item.title}</p>
                        <p className="text-[12px] text-gray-500">{item.sub}</p>
                      </div>
                      <div
                        className={`flex items-center gap-1 text-sm font-medium opacity-70 group-hover:opacity-100 transition-opacity ${t.accent}`}
                      >
                        <span>{item.action}</span>
                        <ChevronRight
                          size={14}
                          className="transition-transform group-hover:translate-x-0.5"
                        />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </Layout>
  );
}
