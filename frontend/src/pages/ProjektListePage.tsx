import { useQuery, useSubscription } from "@apollo/client/react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, ChevronsUpDown, ChevronUp, ChevronDown, Plus, Search, UserRound } from "lucide-react";
import Layout from "../components/Layout";
import { GET_PROJEKTE } from "../graphql/queries";
import { PROJEKT_LISTE_SUBSCRIPTION } from "../graphql/subscriptions";
import { chf, type GQLMeasurement } from "../utils/format";
import { getDeviation, DEV_STYLES } from "../utils/deviation";
import { useAuth } from "../contexts/AuthContext";
import { canCreateProject, canViewFinancials } from "../utils/permissions";

type Projekt = {
  id: string;
  auftragsnummer: string;
  name: string;
  offerteSumme: GQLMeasurement;
  wvSumme: GQLMeasurement | null;
  auftragFertig: boolean;
  projektleiter: string | null;
  projektKennzahlenList: { items: { summeWvPlus: GQLMeasurement | null; summeIstKosten: GQLMeasurement | null }[] };
};

type QueryData = {
  projektList: { items: Projekt[]; pageInfo: { totalCount: number } };
};

type SortKey = "auftragsnummer" | "name" | "projektleiter" | "offerteSumme" | "summeWvPlus";
type SortDir = "asc" | "desc";

const DESC_DEFAULT = new Set<SortKey>(["offerteSumme", "summeWvPlus"]);

const AVATAR_COLORS = [
  "bg-blue-100 text-blue-700",
  "bg-violet-100 text-violet-700",
  "bg-emerald-100 text-emerald-700",
  "bg-amber-100 text-amber-700",
  "bg-rose-100 text-rose-700",
];

function avatarColor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}

function Avatar({ name }: { name: string | null }) {
  if (!name) {
    return (
      <span className="inline-flex items-center gap-2 text-gray-400">
        <span className="w-7 h-7 rounded-full bg-gray-100 border border-dashed border-gray-300 inline-flex items-center justify-center">
          <UserRound size={13} className="text-gray-400" />
        </span>
        <span className="text-[12px] italic">Nicht zugewiesen</span>
      </span>
    );
  }
  const initials = name.slice(0, 2).toUpperCase();
  const colorCls = avatarColor(name);
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`w-7 h-7 rounded-full inline-flex items-center justify-center font-semibold text-[11px] ${colorCls}`}>
        {initials}
      </span>
      <span className="text-sm text-gray-800">{name}</span>
    </span>
  );
}

function StatusBadge({ archived }: { archived: boolean }) {
  if (archived) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-50 text-gray-500 ring-1 ring-inset ring-gray-200">
        <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
        Archiviert
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
      Aktiv
    </span>
  );
}

function DeviationCell({ wv, ist }: { wv: number | null; ist: number | null }) {
  if (wv == null || ist == null || ist === 0) {
    return <span className="text-gray-300 text-[12px]">–</span>;
  }
  const dev = getDeviation(wv, ist);
  if (!dev) return <span className="text-gray-300 text-[12px]">–</span>;

  const magnitude = Math.min(Math.abs(dev.overPct), 30) / 30;
  const fillPct = magnitude * 50;
  const isOver = dev.overPct > 0;
  const dotColor = DEV_STYLES[dev.level].dot;
  const textColor = DEV_STYLES[dev.level].text;
  const sign = dev.overPct >= 0 ? "+" : "−";
  const absStr = Math.abs(dev.overPct).toFixed(1);

  return (
    <div className="flex items-center gap-2">
      <div className="relative w-12 h-1.5 rounded-full bg-gray-100 shrink-0">
        <div className="absolute left-1/2 top-[-2px] bottom-[-2px] w-px bg-gray-400/60" />
        <div
          className={`absolute top-0 bottom-0 rounded-full ${dotColor}`}
          style={{
            width: `${fillPct}%`,
            left: isOver ? "50%" : `${50 - fillPct}%`,
          }}
        />
      </div>
      <span className={`text-[12px] font-medium tabular-nums whitespace-nowrap ${textColor}`}>
        {sign}{absStr} %
      </span>
    </div>
  );
}

function SortIcon({ active, dir, hovered }: { active: boolean; dir: SortDir; hovered: boolean }) {
  if (active) {
    return dir === "asc"
      ? <ChevronUp size={13} className="inline ml-1 opacity-100" />
      : <ChevronDown size={13} className="inline ml-1 opacity-100" />;
  }
  return <ChevronsUpDown size={13} className={`inline ml-1 transition-opacity ${hovered ? "opacity-100" : "opacity-30"}`} />;
}

function sortProjekte(items: Projekt[], key: SortKey, dir: SortDir): Projekt[] {
  return [...items].sort((a, b) => {
    let va: string | number;
    let vb: string | number;
    if (key === "offerteSumme") {
      va = Number(a.offerteSumme?.value ?? 0);
      vb = Number(b.offerteSumme?.value ?? 0);
    } else if (key === "summeWvPlus") {
      va = a.projektKennzahlenList.items[0]?.summeWvPlus?.value ?? 0;
      vb = b.projektKennzahlenList.items[0]?.summeWvPlus?.value ?? 0;
    } else if (key === "projektleiter") {
      va = a.projektleiter ?? "￿";
      vb = b.projektleiter ?? "￿";
    } else {
      va = (a[key] ?? "") as string;
      vb = (b[key] ?? "") as string;
    }
    if (va < vb) return dir === "asc" ? -1 : 1;
    if (va > vb) return dir === "asc" ? 1 : -1;
    return 0;
  });
}

export default function ProjektListePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const showFinancials = canViewFinancials(user);
  const showCreateButton = canCreateProject(user);

  const [sortKey, setSortKey] = useState<SortKey>("auftragsnummer");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [hoveredHeader, setHoveredHeader] = useState<SortKey | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const { data, loading, error, refetch } = useQuery<QueryData>(GET_PROJEKTE, {
    fetchPolicy: "network-only",
  });

  useSubscription(PROJEKT_LISTE_SUBSCRIPTION, {
    onData: () => refetch(),
  });

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(DESC_DEFAULT.has(key) ? "desc" : "asc");
    }
  }

  const q = searchQuery.trim().toLowerCase();
  const filtered = (data?.projektList.items ?? []).filter((p) => {
    if (!q) return true;
    return (
      p.name.toLowerCase().includes(q) ||
      p.auftragsnummer.toLowerCase().includes(q) ||
      (p.projektleiter ?? "").toLowerCase().includes(q)
    );
  });
  const items = sortProjekte(filtered, sortKey, sortDir);
  const total = data?.projektList.pageInfo.totalCount ?? 0;

  const thBase = (key: SortKey) =>
    `px-4 py-3 text-[11px] uppercase tracking-wider font-semibold select-none cursor-pointer transition-colors whitespace-nowrap ${
      sortKey === key ? "text-blue-700" : "text-gray-500 hover:text-gray-900"
    }`;

  return (
    <Layout>
      {/* Page header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-[22px] font-semibold text-gray-900">Projekte</h1>
          {data && (
            <p className="text-[12px] text-gray-500 mt-0.5">
            {q ? `${items.length} von ${total} Projekten` : `${total} Projekte`}
          </p>
          )}
        </div>
        {showCreateButton && (
          <button
            type="button"
            onClick={() => navigate("/projekte/neu")}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium text-white transition-colors"
            style={{ backgroundColor: "var(--forge-blue)" }}
          >
            <Plus size={15} />
            Neues Projekt
          </button>
        )}
      </div>

      {loading &&<p className="text-sm text-gray-500">Lade Projekte…</p>}

      {error && (
        <p
          className="rounded-lg p-4 border text-sm"
          style={{ color: "var(--forge-red)", borderColor: "var(--forge-red)", backgroundColor: "var(--forge-red-soft)" }}
        >
          Fehler: {error.message}
        </p>
      )}

      {data && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          {/* Suchfeld — innerhalb der Card, mit border-b zur Tabelle */}
          <div className="px-4 py-3 border-b border-gray-200">
            <div className="relative max-w-sm">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              <input
                type="text"
                placeholder="Suche nach Name, Auftragsnr. oder Projektleiter…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-8 py-2 text-sm rounded-md border border-gray-200 bg-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                  aria-label="Suche zurücksetzen"
                >
                  ×
                </button>
              )}
            </div>
          </div>

          {items.length === 0 ? (
            <div className="px-6 py-16 flex flex-col items-center text-center">
              <svg
                viewBox="0 0 80 80"
                className="text-gray-300 mb-4"
                width="80"
                height="80"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <rect x="8" y="20" width="64" height="48" rx="4" />
                <path d="M8 32h64M24 20v-4a4 4 0 0 1 4-4h24a4 4 0 0 1 4 4v4" />
                <line x1="28" y1="50" x2="52" y2="50" />
                <line x1="28" y1="58" x2="44" y2="58" />
              </svg>
              {q ? (
                <>
                  <p className="text-[15px] font-semibold text-gray-900 mb-1">Keine Treffer</p>
                  <p className="text-sm text-gray-500 max-w-xs mb-4">
                    Kein Projekt passt zu „{searchQuery}".
                  </p>
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    Suche zurücksetzen
                  </button>
                </>
              ) : (
                <>
                  <p className="text-[15px] font-semibold text-gray-900 mb-1">Noch keine Projekte</p>
                  <p className="text-sm text-gray-500 max-w-xs mb-4">
                    Leg dein erstes Projekt an, um Offerten und Kostenpositionen zu erfassen.
                  </p>
                  {showCreateButton && (
                    <button
                      type="button"
                      onClick={() => navigate("/projekte/neu")}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium text-white"
                      style={{ backgroundColor: "var(--forge-blue)" }}
                    >
                      <Plus size={15} />
                      Erstes Projekt anlegen
                    </button>
                  )}
                </>
              )}
            </div>
          ) : (
            <table className="w-full text-sm">
              <colgroup>
                <col style={{ width: "10%" }} />
                <col style={{ width: "28%" }} />
                <col style={{ width: "16%" }} />
                {showFinancials && (
                  <>
                    <col style={{ width: "12%" }} />
                    <col style={{ width: "12%" }} />
                    <col style={{ width: "12%" }} />
                  </>
                )}
                <col style={{ width: "10%" }} />
              </colgroup>
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th
                    className={thBase("auftragsnummer")}
                    onClick={() => handleSort("auftragsnummer")}
                    onMouseEnter={() => setHoveredHeader("auftragsnummer")}
                    onMouseLeave={() => setHoveredHeader(null)}
                  >
                    Auftragsnr.
                    <SortIcon active={sortKey === "auftragsnummer"} dir={sortDir} hovered={hoveredHeader === "auftragsnummer"} />
                  </th>
                  <th
                    className={thBase("name")}
                    onClick={() => handleSort("name")}
                    onMouseEnter={() => setHoveredHeader("name")}
                    onMouseLeave={() => setHoveredHeader(null)}
                  >
                    Name
                    <SortIcon active={sortKey === "name"} dir={sortDir} hovered={hoveredHeader === "name"} />
                  </th>
                  <th
                    className={thBase("projektleiter")}
                    onClick={() => handleSort("projektleiter")}
                    onMouseEnter={() => setHoveredHeader("projektleiter")}
                    onMouseLeave={() => setHoveredHeader(null)}
                  >
                    Projektleiter
                    <SortIcon active={sortKey === "projektleiter"} dir={sortDir} hovered={hoveredHeader === "projektleiter"} />
                  </th>
                  {showFinancials && (
                    <>
                      <th
                        className={`${thBase("offerteSumme")} text-right`}
                        onClick={() => handleSort("offerteSumme")}
                        onMouseEnter={() => setHoveredHeader("offerteSumme")}
                        onMouseLeave={() => setHoveredHeader(null)}
                      >
                        Offerte
                        <SortIcon active={sortKey === "offerteSumme"} dir={sortDir} hovered={hoveredHeader === "offerteSumme"} />
                      </th>
                      <th
                        className={`${thBase("summeWvPlus")} text-right`}
                        onClick={() => handleSort("summeWvPlus")}
                        onMouseEnter={() => setHoveredHeader("summeWvPlus")}
                        onMouseLeave={() => setHoveredHeader(null)}
                      >
                        WV + Zusätze
                        <SortIcon active={sortKey === "summeWvPlus"} dir={sortDir} hovered={hoveredHeader === "summeWvPlus"} />
                      </th>
                      <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                        Abweichung zu Ist
                      </th>
                    </>
                  )}
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => navigate(`/projekte/${p.id}`)}
                    className="border-b border-gray-100 last:border-0 hover:bg-blue-50/50 cursor-pointer transition-colors group"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">
                      {p.auftragsnummer}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <span className="inline-flex items-center gap-1">
                        {p.name}
                        <ChevronRight
                          size={14}
                          className="text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity -translate-x-1 group-hover:translate-x-0 duration-150"
                        />
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Avatar name={p.projektleiter} />
                    </td>
                    {showFinancials && (
                      <>
                        <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                          {chf(p.offerteSumme, { withCurrency: false })}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                          {p.projektKennzahlenList.items[0]?.summeWvPlus != null ? chf(p.projektKennzahlenList.items[0].summeWvPlus, { withCurrency: false }) : "–"}
                        </td>
                        <td className="px-4 py-3">
                          <DeviationCell wv={p.projektKennzahlenList.items[0]?.summeWvPlus?.value ?? null} ist={p.projektKennzahlenList.items[0]?.summeIstKosten?.value ?? null} />
                        </td>
                      </>
                    )}
                    <td className="px-4 py-3">
                      <StatusBadge archived={p.auftragFertig} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </Layout>
  );
}
