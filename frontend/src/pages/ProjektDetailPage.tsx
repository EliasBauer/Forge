import { useMutation, useQuery, useSubscription } from "@apollo/client/react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Calculator, ChevronLeft, Database, Pencil } from "lucide-react";
import Layout from "../components/Layout";
import { GET_KOSTENART_IDS, GET_PROJEKT } from "../graphql/queries";
import {
  CREATE_KOSTEN_POSITION,
  DELETE_KOSTEN_POSITION,
  UPDATE_KOSTEN_POSITION,
  UPDATE_PROJEKT,
} from "../graphql/mutations";
import { PROJEKT_DETAIL_SUBSCRIPTION } from "../graphql/subscriptions";
import { chf, pct, signedPct, type GQLMeasurement } from "../utils/format";
import { getDeviation, DEV_STYLES, type DeviationLevel } from "../utils/deviation";
import { useAuth } from "../contexts/AuthContext";
import { canEdit, canViewFinancials } from "../utils/permissions";

type KostenPosition = {
  id: string;
  art: { schluessel: string };
  offerteKostenWert: GQLMeasurement | null;
  offerteStunden: number | null;
  wvKostenWert: GQLMeasurement | null;
  wvKostenWertProzent: number | null;
  offerteKostenWertProzent: number | null;
};

type IstwertItem = {
  kostenart: { schluessel: string };
  istKostenWert: GQLMeasurement | null;
  istKostenWertProzent: number | null;
};

type ProjektKennzahlen = {
  summeOfferteKosten: GQLMeasurement | null;
  summeWvKosten: GQLMeasurement | null;
  summeIstKosten: GQLMeasurement | null;
  verbrauchsrate: number | null;
  deltaWvOff: GQLMeasurement | null;
  deltaWvOffPct: number | null;
  deltaIstPlan: GQLMeasurement | null;
  deltaIstPlanPct: number | null;
  summeWvPlus: GQLMeasurement | null;
  bisherVerrechnet: GQLMeasurement | null;
};

type Projekt = {
  id: string;
  name: string;
  auftragsnummer: string;
  jahr: number;
  offerteSumme: GQLMeasurement;
  wvSumme: GQLMeasurement | null;
  auftragFertig: boolean;
  projektleiter: string | null;
  projektKennzahlenList: { items: ProjektKennzahlen[] };
  kostenPositionenList: { items: KostenPosition[] };
  istWertList: { items: IstwertItem[] };
};

type QueryData = { projekt: Projekt | null };
type UpdateProjektResult = { updateProjekt: { success: boolean } };
type UpdateKostenPositionResult = { updateKostenPosition: { success: boolean } };
type CreateKostenPositionResult = { createKostenPosition: { success: boolean } };
type DeleteKostenPositionResult = { deleteKostenPosition: { success: boolean } };
type KostenartIdItem = { id: string; schluessel: string };
type KostenartIdsData = { kostenartList: { items: KostenartIdItem[] } };
type UserOption = { id: number; username: string };
type HeaderForm = { name: string; offerteSumme: string; wvSumme: string; projektleiter: string };

const ART_LABELS: Record<string, string> = {
  regie: "Regie",
  nachtrag: "Nachtrag",
  apparate: "Apparate",
  kanaele_rohre: "Kanäle und Rohre",
  armaturen: "Armaturen",
  regulierung: "Regulierung",
  schaltschrank: "Schaltschrank",
  transport_montage: "Transport und Montage",
  stunden: "Stunden",
  transport_montage_fremd: "Transport und Montage – Fremdleistung",
  isolation: "Isolation",
  dienstleistung: "Dienstleistung",
  diverses: "Diverses",
  planung: "Planung",
  gemeinkosten: "Gemeinkosten",
};

const ERTRAGSBLOCK = new Set(["regie", "nachtrag"]);

const OFFERTE_EDITIERBAR = new Set([
  "apparate", "kanaele_rohre", "armaturen", "regulierung", "schaltschrank",
  "transport_montage", "transport_montage_fremd", "isolation",
  "dienstleistung", "diverses", "planung", "gemeinkosten",
]);

const KOSTEN_REIHENFOLGE = [
  "regie", "nachtrag",
  "apparate", "kanaele_rohre", "armaturen", "regulierung", "schaltschrank",
  "transport_montage", "stunden", "transport_montage_fremd",
  "isolation", "dienstleistung", "diverses", "planung", "gemeinkosten",
];

// Column CSS helpers
const clsCalc = "bg-gray-50 text-gray-500 text-right text-sm tabular-nums px-3 py-1.5";
const clsCalcH = "bg-gray-50 px-3 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right";
const clsErpH = "bg-blue-50 px-3 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right";

// Pair group dividers (inset box-shadow so they overlay cell backgrounds)
const pairDiv: React.CSSProperties = { boxShadow: "inset 1px 0 0 #e5e7eb", paddingLeft: "1.25rem" };
// Stronger divider between Art (col1) and Soll-Offerte (col2)
const artDiv: React.CSSProperties = { boxShadow: "inset 2px 0 0 #d1d5db", paddingLeft: "1.5rem" };

const errorStyle: React.CSSProperties = {
  color: "var(--forge-red)",
  borderColor: "var(--forge-red)",
  backgroundColor: "var(--forge-red-soft)",
};

function formatStunden(val: number | null | undefined): string {
  if (val == null) return "–";
  return `${val.toFixed(2)} h`;
}

function parseCHF(raw: string): string | null {
  if (!raw.trim()) return null;
  const n = parseFloat(raw.replace(/['']/g, "").replace(",", "."));
  if (isNaN(n) || n < 0) return null;
  return `${n.toFixed(2)} CHF`;
}

function SignedAmount({
  value,
  polarity = "neg-bad",
  withCurrency = true,
}: {
  value: number | null | undefined;
  polarity?: "neg-bad" | "pos-bad";
  withCurrency?: boolean;
}) {
  if (value == null) return <span className="text-gray-400 tabular-nums">–</span>;
  const isNeg = value < 0;
  const isGood = polarity === "neg-bad" ? !isNeg : isNeg;
  const cls = value === 0 ? "text-gray-700" : isGood ? "text-emerald-700" : "text-rose-700";
  return <span className={`tabular-nums ${cls}`}>{chf(value, { withCurrency })}</span>;
}

function SignedPctCell({
  value,
  polarity = "neg-bad",
}: {
  value: number | null | undefined;
  polarity?: "neg-bad" | "pos-bad";
}) {
  const { text, colorClass } = signedPct(value, polarity);
  return <span className={`tabular-nums ${colorClass}`}>{text}</span>;
}

// Ist-cell background + text based on heatmap deviation level
function istCellCls(level: DeviationLevel | null): string {
  if (level === null) return "bg-blue-50 text-blue-700";
  if (level === "over") return "bg-rose-50 text-rose-700 font-medium";
  if (level === "warn") return "bg-amber-50 text-amber-700 font-medium";
  return "bg-emerald-50/60 text-emerald-700 font-medium";
}

// ------- Visualization card -------

type VizRow = {
  schluessel: string;
  label: string;
  planWV: number | null;
  ist: number | null;
};

function ProjectVisualization({ rows }: { rows: VizRow[] }) {
  const visible = rows.filter((r) => r.planWV != null || r.ist != null);
  if (visible.length === 0) return null;

  const maxVal = Math.max(
    ...visible.flatMap((r) => [r.planWV ?? 0, r.ist ?? 0]),
    1,
  );

  const deviations = visible.map((r) => getDeviation(r.planWV, r.ist));
  const countOver = deviations.filter((d) => d?.level === "over").length;
  const countWarn = deviations.filter((d) => d?.level === "warn").length;
  const countOk = deviations.filter((d) => d != null && (d.level === "ok" || d.level === "under")).length;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm mt-5">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h2 className="text-[15px] font-semibold text-gray-900">Projektstatus auf einen Blick</h2>
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
        <p className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-4">
          Plan-WV vs. Ist je Kategorie
        </p>
        <div className="flex flex-col gap-3">
          {visible.map((row, i) => {
            const dev = deviations[i];
            const level = dev?.level ?? null;
            const planWVPct = row.planWV != null ? (row.planWV / maxVal) * 100 : 0;
            const istPct = row.ist != null ? (row.ist / maxVal) * 100 : 0;
            const dotColor = level ? DEV_STYLES[level].dot : "bg-gray-400";
            const textColor = level ? DEV_STYLES[level].text : "text-gray-400";

            return (
              <div
                key={row.schluessel}
                className="grid items-center gap-4 py-2 border-b border-gray-50 last:border-0"
                style={{ gridTemplateColumns: "160px 1fr 130px" }}
              >
                {/* Label with status dot */}
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${level ? DEV_STYLES[level].dot : "bg-gray-200"}`} />
                  <span className="text-sm text-gray-700 truncate">{row.label}</span>
                </div>

                {/* Dual bar */}
                <div className="flex flex-col gap-1.5">
                  {/* Plan-WV bar */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-gray-400 w-11 text-right shrink-0">Plan-WV</span>
                    <div className="flex-1 h-2.5 rounded-sm bg-gray-100 relative overflow-hidden">
                      <div
                        className="absolute left-0 top-0 h-full rounded-sm bg-gray-300"
                        style={{ width: `${planWVPct}%` }}
                      />
                    </div>
                    <span className="text-[11px] text-gray-500 tabular-nums w-24 text-right shrink-0">
                      {chf(row.planWV)}
                    </span>
                  </div>
                  {/* Ist bar + Plan-WV marker */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-gray-400 w-11 text-right shrink-0">Ist</span>
                    <div className="flex-1 h-2.5 rounded-sm bg-gray-100 relative overflow-visible">
                      <div
                        className={`absolute left-0 top-0 h-full rounded-sm ${dotColor}`}
                        style={{ width: `${istPct}%` }}
                      />
                      {planWVPct > 0 && (
                        <div
                          className="absolute top-[-2px] bottom-[-2px] w-px bg-gray-500/70"
                          style={{ left: `${planWVPct}%` }}
                        />
                      )}
                    </div>
                    <span className="text-[11px] text-gray-500 tabular-nums w-24 text-right shrink-0">
                      {chf(row.ist)}
                    </span>
                  </div>
                </div>

                {/* Status pill */}
                <div className="flex justify-end">
                  {dev != null ? (
                    <span className={`inline-flex items-center gap-1 text-[11px] font-medium tabular-nums ${textColor}`}>
                      {(level === "over" || level === "warn") && (
                        <span className="text-[10px]">⚠</span>
                      )}
                      {dev.overPct >= 0 ? "+" : "−"}
                      {Math.abs(dev.overPct).toFixed(1)} %
                    </span>
                  ) : row.planWV != null ? (
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

// ------- Main page -------

export default function ProjektDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const showFinancials = canViewFinancials(user);
  const canEditData = canEdit(user);

  const { data, loading, error, refetch } = useQuery<QueryData>(GET_PROJEKT, {
    variables: { id },
    skip: !id,
  });

  const { data: kostenartData } = useQuery<KostenartIdsData>(GET_KOSTENART_IDS);
  const artIdMap = new Map<string, string>(
    kostenartData?.kostenartList.items.map((a) => [a.schluessel, a.id]) ?? [],
  );

  useSubscription(PROJEKT_DETAIL_SUBSCRIPTION, {
    variables: { id },
    skip: !id,
    onData: () => { refetch(); },
  });

  const [editingHeader, setEditingHeader] = useState(false);
  const [headerForm, setHeaderForm] = useState<HeaderForm | null>(null);
  const [editingPos, setEditingPos] = useState<{
    id: string | null;
    artId: string;
    art: string;
    value: string;
  } | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const skipPosBlurRef = useRef(false);
  const [users, setUsers] = useState<UserOption[]>([]);

  useEffect(() => {
    if (canEditData) {
      fetch("/api/users/")
        .then((r) => (r.ok ? r.json() : []))
        .then((d: UserOption[]) => setUsers(d))
        .catch(() => {});
    }
  }, [canEditData]);

  const [updateProjekt, { loading: savingHeader }] =
    useMutation<UpdateProjektResult>(UPDATE_PROJEKT, {
      onCompleted(result) {
        if (result.updateProjekt.success) { setEditingHeader(false); setHeaderForm(null); setMutationError(null); refetch(); }
        else setMutationError("Speichern fehlgeschlagen.");
      },
      onError(err) { setMutationError(err.message); },
    });

  const [updateKostenPosition, { loading: savingUpdate }] =
    useMutation<UpdateKostenPositionResult>(UPDATE_KOSTEN_POSITION, {
      onCompleted(result) {
        if (result.updateKostenPosition.success) { setEditingPos(null); setMutationError(null); refetch(); }
        else setMutationError("Speichern fehlgeschlagen.");
      },
      onError(err) { setMutationError(err.message); },
    });

  const [createKostenPosition, { loading: savingCreate }] =
    useMutation<CreateKostenPositionResult>(CREATE_KOSTEN_POSITION, {
      onCompleted(result) {
        if (result.createKostenPosition.success) { setEditingPos(null); setMutationError(null); refetch(); }
        else setMutationError("Speichern fehlgeschlagen.");
      },
      onError(err) { setMutationError(err.message); },
    });

  const [deleteKostenPosition, { loading: savingDelete }] =
    useMutation<DeleteKostenPositionResult>(DELETE_KOSTEN_POSITION, {
      onCompleted(result) {
        if (result.deleteKostenPosition.success) { setEditingPos(null); setMutationError(null); refetch(); }
        else setMutationError("Löschen fehlgeschlagen.");
      },
      onError(err) { setMutationError(err.message); },
    });

  const savingPos = savingUpdate || savingCreate || savingDelete;

  const p = data?.projekt;
  const kennzahlen = p?.projektKennzahlenList.items[0] ?? null;
  const posMap = new Map(p ? p.kostenPositionenList.items.map((pos) => [pos.art.schluessel, pos]) : []);
  const istWertMap = new Map(p ? p.istWertList.items.map((item) => [item.kostenart.schluessel, item]) : []);
  const allReihen = KOSTEN_REIHENFOLGE.map((schluessel) => ({ schluessel, pos: posMap.get(schluessel) ?? null }));
  const visibleReihen = showFinancials ? allReihen : allReihen.filter((r) => r.schluessel === "stunden");

  const summeOfferteKosten = kennzahlen?.summeOfferteKosten?.value ?? 0;
  const summeWvKosten = kennzahlen?.summeWvKosten?.value ?? 0;
  const summeIstKosten = kennzahlen?.summeIstKosten?.value ?? 0;
  const verbrauchsrate = kennzahlen?.verbrauchsrate ?? null;
  const deltaWvOff = kennzahlen?.deltaWvOff?.value ?? null;
  const deltaWvOffPct = kennzahlen?.deltaWvOffPct ?? null;
  const deltaPlanWv = 0; // Plan-WV = WV until backend ready
  const deltaPlanWvPct = 0;
  const deltaIstPlan = kennzahlen?.deltaIstPlan?.value ?? null;
  const deltaIstPlanPct = kennzahlen?.deltaIstPlanPct ?? null;

  const offerteSummeNum = p ? Number(p.offerteSumme.value) : null;
  const wvSummeNum = p?.wvSumme ? Number(p.wvSumme.value) : null;

  // Visualization rows (non-locked, with at least one value)
  const vizRows: VizRow[] = allReihen
    .filter((r) => !ERTRAGSBLOCK.has(r.schluessel) && r.schluessel !== "stunden")
    .map((r) => ({
      schluessel: r.schluessel,
      label: ART_LABELS[r.schluessel] ?? r.schluessel,
      planWV: r.pos?.wvKostenWert?.value ?? null,
      ist: istWertMap.get(r.schluessel)?.istKostenWert?.value ?? null,
    }))
    .filter((r) => r.planWV != null || r.ist != null);

  function startEditHeader() {
    if (!p) return;
    setHeaderForm({
      name: p.name,
      offerteSumme: String(p.offerteSumme.value),
      wvSumme: p.wvSumme ? String(p.wvSumme.value) : "",
      projektleiter: users.find((u) => u.username === p.projektleiter)
        ? String(users.find((u) => u.username === p.projektleiter)!.id) : "",
    });
    setEditingHeader(true);
    setMutationError(null);
  }

  function cancelEditHeader() {
    setEditingHeader(false);
    setHeaderForm(null);
    setMutationError(null);
  }

  function saveHeader() {
    if (!p || !headerForm) return;
    const offerteSumme = parseCHF(headerForm.offerteSumme);
    const wvSumme = parseCHF(headerForm.wvSumme);
    if (!offerteSumme) { setMutationError("Bitte eine gültige Offerte-Summe eingeben."); return; }
    if (headerForm.wvSumme.trim() && !wvSumme) { setMutationError("Bitte eine gültige WV-Summe eingeben."); return; }
    updateProjekt({ variables: { id: p.id, name: headerForm.name, offerteSumme, wvSumme: wvSumme ?? undefined, projektleiter: headerForm.projektleiter || undefined } });
  }

  function toggleArchivieren() {
    if (!p) return;
    updateProjekt({ variables: { id: p.id, auftragFertig: !p.auftragFertig } });
  }

  function startEditPos(schluessel: string, pos: KostenPosition | null) {
    setEditingPos({
      id: pos?.id ?? null,
      artId: artIdMap.get(schluessel) ?? "",
      art: schluessel,
      value: pos?.offerteKostenWert ? String(pos.offerteKostenWert.value) : "",
    });
    setMutationError(null);
  }

  function savePos() {
    if (!editingPos || !p) return;
    const offerteKostenWert = parseCHF(editingPos.value);
    if (editingPos.id !== null) {
      if (!offerteKostenWert) deleteKostenPosition({ variables: { id: editingPos.id } });
      else updateKostenPosition({ variables: { id: editingPos.id, offerteKostenWert } });
    } else {
      if (!offerteKostenWert) { setEditingPos(null); return; }
      createKostenPosition({ variables: { projekt: p.id, art: editingPos.artId, offerteKostenWert } });
    }
  }

  function handlePosKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") { skipPosBlurRef.current = true; savePos(); }
    if (e.key === "Escape") { skipPosBlurRef.current = true; setEditingPos(null); setMutationError(null); }
  }

  function handlePosBlur() {
    if (skipPosBlurRef.current) { skipPosBlurRef.current = false; return; }
    savePos();
  }

  function handleHeaderKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") saveHeader();
    if (e.key === "Escape") cancelEditHeader();
  }

  const headerInputClass = "font-medium text-gray-800 tabular-nums border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none w-full";

  // Footer helper: calc cell with optional content
  const footerCalc = (content: React.ReactNode, extraStyle?: React.CSSProperties) => (
    <td className={clsCalc.replace("py-1.5", "py-2.5")} style={extraStyle}>{content ?? ""}</td>
  );
  const footerErp = (content: React.ReactNode, extraStyle?: React.CSSProperties) => (
    <td className="bg-blue-50 text-blue-700 px-3 py-2.5 text-right tabular-nums text-sm" style={extraStyle}>{content ?? ""}</td>
  );

  return (
    <Layout>
      {/* Breadcrumb */}
      <div className="mb-4">
        <Link
          to="/projekte"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors"
        >
          <ChevronLeft size={15} />
          Projekte
        </Link>
      </div>

      {loading && <p className="text-sm text-gray-500">Lade Projekt…</p>}
      {error && <p className="rounded-lg p-4 border text-sm" style={errorStyle}>Fehler: {error.message}</p>}
      {mutationError && <p className="rounded-lg p-4 border text-sm mb-4" style={errorStyle}>{mutationError}</p>}

      {p && (
        <>
          {/* Projekt-Header-Card */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm mb-5">
            <div className="px-6 pt-5 pb-4 flex items-start justify-between">
              <div>
                {editingHeader && headerForm ? (
                  <input
                    type="text"
                    value={headerForm.name}
                    onChange={(e) => setHeaderForm((f) => (f ? { ...f, name: e.target.value } : f))}
                    onKeyDown={handleHeaderKeyDown}
                    className="text-[22px] font-semibold text-gray-900 border-b border-gray-400 focus:outline-none w-full mb-1"
                  />
                ) : (
                  <h1 className="text-[22px] font-semibold text-gray-900">{p.name}</h1>
                )}
                <p className="text-xs text-gray-500 mt-1">{p.auftragsnummer} (id:{p.id})</p>
              </div>
              <div className="flex items-center gap-2 ml-4 shrink-0">
                {!editingHeader && p.auftragFertig && (
                  <span className="rounded px-2.5 py-1 text-xs font-medium bg-gray-100 text-gray-600">Fertig</span>
                )}
                {canEditData && !editingHeader && (
                  <>
                    <button type="button" onClick={startEditHeader}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 rounded-md text-gray-700 hover:bg-gray-50 transition-colors">
                      <Pencil size={13} />Bearbeiten
                    </button>
                    <button type="button" onClick={toggleArchivieren} disabled={savingHeader}
                      className="px-3 py-1.5 text-sm border border-gray-200 rounded-md text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50">
                      {p.auftragFertig ? "Reaktivieren" : "Archivieren"}
                    </button>
                  </>
                )}
                {editingHeader && (
                  <>
                    <button type="button" onClick={saveHeader} disabled={savingHeader}
                      className="px-3 py-1.5 text-sm rounded-md text-white disabled:opacity-50"
                      style={{ backgroundColor: "var(--forge-blue)" }}>
                      {savingHeader ? "…" : "Speichern"}
                    </button>
                    <button type="button" onClick={cancelEditHeader}
                      className="px-3 py-1.5 text-sm border border-gray-200 rounded-md text-gray-700 hover:bg-gray-50 transition-colors">
                      Abbrechen
                    </button>
                  </>
                )}
              </div>
            </div>

            <div className="border-t border-gray-100 px-6 py-5 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-6">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-gray-500 font-medium">Projektleiter</div>
                {editingHeader && headerForm ? (
                  <select value={headerForm.projektleiter}
                    onChange={(e) => setHeaderForm((f) => f ? { ...f, projektleiter: e.target.value } : f)}
                    className="text-[15px] text-gray-900 mt-1 border border-gray-300 rounded px-2 py-1 bg-white focus:outline-none w-full text-sm">
                    <option value="">– kein –</option>
                    {users.map((u) => <option key={u.id} value={String(u.id)}>{u.username}</option>)}
                  </select>
                ) : (
                  <div className="mt-1 text-[15px] text-gray-900">{p.projektleiter ?? "–"}</div>
                )}
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-gray-500 font-medium">Jahr</div>
                <div className="mt-1 text-[15px] text-gray-900 tabular-nums">{p.jahr}</div>
              </div>
              {showFinancials && (
                <>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-gray-500 font-medium">Offerte exkl. MwSt.</div>
                    {editingHeader && headerForm ? (
                      <input type="text" inputMode="decimal" value={headerForm.offerteSumme}
                        onChange={(e) => setHeaderForm((f) => f ? { ...f, offerteSumme: e.target.value } : f)}
                        onKeyDown={handleHeaderKeyDown} className={headerInputClass + " mt-1"} placeholder="0.00" />
                    ) : (
                      <div className="mt-1 text-[15px] text-gray-900 tabular-nums">{chf(p.offerteSumme)}</div>
                    )}
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-gray-500 font-medium">WV-Summe exkl. MwSt.</div>
                    {editingHeader && headerForm ? (
                      <input type="text" inputMode="decimal" value={headerForm.wvSumme}
                        onChange={(e) => setHeaderForm((f) => f ? { ...f, wvSumme: e.target.value } : f)}
                        onKeyDown={handleHeaderKeyDown} className={headerInputClass + " mt-1"} placeholder="0.00 (optional)" />
                    ) : (
                      <div className="mt-1 text-[15px] text-gray-900 tabular-nums">{chf(p.wvSumme)}</div>
                    )}
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-gray-500 font-medium">Plan-WV-Summe exkl. MwSt.</div>
                    {/* Plan-WV = WV-Summe until backend ready */}
                    <div className="mt-1 text-[15px] text-gray-900 tabular-nums">{chf(p.wvSumme)}</div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Kostenpositionen-Card */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-[15px] font-semibold text-gray-900">
                {showFinancials ? "Kostenpositionen" : "Stunden"}
              </h2>
              {showFinancials && (
                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-sm border border-gray-300 bg-white inline-block" />editierbar
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-sm border border-gray-200 bg-gray-100 inline-block" />berechnet
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-sm border border-blue-200 bg-blue-50 inline-block" />aus ERP
                  </span>
                </div>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-white">
                    <th className="px-6 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-left w-[24%]">Art</th>
                    {showFinancials && (
                      <>
                        <th className="px-3 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right" style={artDiv}>
                          <span className="inline-flex items-center justify-end gap-1"><Pencil size={11} className="text-gray-400" />Soll-Offerte</span>
                        </th>
                        <th className={clsCalcH}>
                          <span className="inline-flex items-center justify-end gap-1"><Calculator size={11} />%</span>
                        </th>
                        <th className={clsCalcH} style={pairDiv}>
                          <span className="inline-flex items-center justify-end gap-1"><Calculator size={11} />Soll-WV</span>
                        </th>
                        <th className={clsCalcH}>
                          <span className="inline-flex items-center justify-end gap-1"><Calculator size={11} />%</span>
                        </th>
                        <th className={clsCalcH} style={pairDiv}>
                          <span className="inline-flex items-center justify-end gap-1"><Calculator size={11} />Plan-WV</span>
                        </th>
                        <th className={clsCalcH}>
                          <span className="inline-flex items-center justify-end gap-1"><Calculator size={11} />%</span>
                        </th>
                        <th className={clsErpH} style={pairDiv}>
                          <span className="inline-flex items-center justify-end gap-1.5">
                            <Database size={11} />Ist
                            <span className="text-[9px] font-bold uppercase tracking-wider px-1 rounded"
                              style={{ backgroundColor: "#dbeafe", color: "#1d4ed8", border: "1px solid #bfdbfe" }}>ERP</span>
                          </span>
                        </th>
                        <th className={clsErpH}>
                          <span className="inline-flex items-center justify-end gap-1"><Database size={11} />%</span>
                        </th>
                      </>
                    )}
                    {!showFinancials && (
                      <>
                        <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right">Ist</th>
                        <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right">Ist %</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {visibleReihen.map(({ schluessel, pos }, i) => {
                    const isErtragsblock = ERTRAGSBLOCK.has(schluessel);
                    const isStunden = schluessel === "stunden";
                    const prevIsErtragsblock = i > 0 && ERTRAGSBLOCK.has(visibleReihen[i - 1].schluessel);
                    const showDivider = !isErtragsblock && prevIsErtragsblock;

                    const isEditingThisPos = pos !== null
                      ? editingPos?.id === pos.id
                      : editingPos?.art === schluessel && editingPos?.id === null;
                    const canEditPos = canEditData && OFFERTE_EDITIERBAR.has(schluessel);

                    const sollOfferteVal = pos === null ? null : isStunden ? null : pos.offerteKostenWert;
                    const sollWvDisplay = pos === null ? "–"
                      : isStunden ? formatStunden(pos.wvKostenWert?.value)
                      : pos.wvKostenWert != null ? chf(pos.wvKostenWert) : "–";

                    // Heatmap: getDeviation(planWV, ist) — Plan-WV = wvKostenWert for now
                    const istWert = istWertMap.get(schluessel) ?? null;
                    const planWVVal = pos?.wvKostenWert?.value ?? null;
                    const istVal = istWert?.istKostenWert?.value ?? null;
                    const dev = (!isErtragsblock && !isStunden) ? getDeviation(planWVVal, istVal) : null;
                    const devLevel = dev?.level ?? null;

                    const istCls = `${istCellCls(devLevel)} text-right text-sm tabular-nums px-3 py-1.5`;
                    const istDisplay = istWert?.istKostenWert == null ? "–"
                      : istWert.istKostenWert.unit === "h" ? formatStunden(istWert.istKostenWert.value)
                      : chf(istWert.istKostenWert);

                    return (
                      <tr
                        key={schluessel}
                        className={`border-b border-gray-100 last:border-0 hover:bg-gray-50/40 ${showDivider ? "border-t-2 border-t-gray-200" : ""}`}
                      >
                        {/* Art + status dot */}
                        <td className={`px-6 py-1.5 text-gray-800${isErtragsblock ? " bg-gray-50" : ""}`}>
                          <span className="inline-flex items-center gap-2">
                            {!isErtragsblock && !isStunden && devLevel && (
                              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${DEV_STYLES[devLevel].dot}`} />
                            )}
                            {ART_LABELS[schluessel] ?? schluessel}
                          </span>
                        </td>

                        {showFinancials && (
                          <>
                            {/* Soll-Offerte */}
                            <td className={`px-3 py-1.5 text-right text-sm${isErtragsblock ? " bg-gray-50" : ""}`} style={artDiv}>
                              {isErtragsblock ? (
                                <span className="text-gray-300 select-none">–</span>
                              ) : isStunden ? (
                                <span className="text-gray-500 tabular-nums">{formatStunden(pos?.offerteStunden)}</span>
                              ) : isEditingThisPos ? (
                                <input
                                  type="text" inputMode="decimal"
                                  value={editingPos!.value}
                                  onChange={(e) => setEditingPos((s) => s ? { ...s, value: e.target.value } : s)}
                                  onKeyDown={handlePosKeyDown} onBlur={handlePosBlur}
                                  autoFocus disabled={savingPos}
                                  className="w-28 text-right border-2 rounded px-2 py-0.5 text-sm focus:outline-none"
                                  style={{ borderColor: "var(--forge-blue)", boxShadow: "0 0 0 3px rgba(74,108,247,0.15)" }}
                                  placeholder="0.00"
                                />
                              ) : canEditPos ? (
                                <div
                                  className="group inline-flex items-center justify-end gap-1 border border-gray-200 rounded px-2 py-0.5 cursor-text hover:border-blue-400 hover:bg-blue-50/40 transition-colors min-w-[7rem]"
                                  onClick={() => { if (!editingPos) startEditPos(schluessel, pos); }}
                                >
                                  <span className="tabular-nums text-gray-900">{chf(sollOfferteVal)}</span>
                                  <Pencil size={11} className="opacity-0 group-hover:opacity-60 text-gray-400 shrink-0 transition-opacity" />
                                </div>
                              ) : (
                                <span className="tabular-nums text-gray-500">{chf(sollOfferteVal)}</span>
                              )}
                            </td>

                            {/* % Soll-Offerte */}
                            <td className={clsCalc}>
                              {pos === null || isErtragsblock || isStunden ? "–" : pct(pos.offerteKostenWertProzent)}
                            </td>

                            {/* Soll-WV */}
                            <td className={clsCalc} style={pairDiv}>{sollWvDisplay}</td>

                            {/* % Soll-WV */}
                            <td className={clsCalc}>
                              {pos === null || isErtragsblock || isStunden ? "–" : pct(pos.wvKostenWertProzent)}
                            </td>

                            {/* Plan-WV = WV */}
                            <td className={clsCalc} style={pairDiv}>{sollWvDisplay}</td>

                            {/* % Plan-WV */}
                            <td className={clsCalc}>
                              {pos === null || isErtragsblock || isStunden ? "–" : pct(pos.wvKostenWertProzent)}
                            </td>

                            {/* Ist — heatmap color */}
                            <td className={istCls} style={pairDiv}>
                              {devLevel === "over" || devLevel === "warn"
                                ? <span className="inline-flex items-center gap-1"><span className="text-[10px]">⚠</span>{istDisplay}</span>
                                : istDisplay}
                            </td>

                            {/* % Ist */}
                            <td className={istCls}>{pct(istWert?.istKostenWertProzent ?? null)}</td>
                          </>
                        )}

                        {!showFinancials && (
                          <>
                            <td className="px-4 py-2 text-right text-gray-700 tabular-nums">{istDisplay}</td>
                            <td className="px-4 py-2 text-right tabular-nums font-medium"
                              style={istWert?.istKostenWertProzent != null && istWert.istKostenWertProzent > 100 ? { color: "var(--forge-red)" } : {}}>
                              {pct(istWert?.istKostenWertProzent ?? null)}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}

                  {/* ── Footer ── */}
                  {showFinancials && p && (
                    <>
                      {/* 1. Summe der Kosten */}
                      <tr className="border-t-2 border-gray-300">
                        <td className="px-6 py-2.5 font-semibold text-gray-900 bg-gray-50/50">Summe der Kosten</td>
                        <td className="px-3 py-2.5 text-right tabular-nums font-semibold text-gray-900" style={artDiv}>{chf(summeOfferteKosten)}</td>
                        {footerCalc("100 %")}
                        {footerCalc(<span className="font-semibold text-gray-900">{chf(summeWvKosten || null)}</span>, { ...pairDiv, backgroundColor: "#f3f4f6" })}
                        {footerCalc("100 %", { backgroundColor: "#f3f4f6" })}
                        {footerCalc(<span className="font-semibold text-gray-900">{chf(summeWvKosten || null)}</span>, { ...pairDiv, backgroundColor: "#f3f4f6" })}
                        {footerCalc("100 %", { backgroundColor: "#f3f4f6" })}
                        {footerErp(<span className="font-semibold">{chf(summeIstKosten || null)}</span>, pairDiv)}
                        {footerErp(<span className="font-semibold">{pct(verbrauchsrate)}</span>)}
                      </tr>

                      {/* 2. Gewinn / Verlust */}
                      <tr className="border-t border-gray-100">
                        <td className="px-6 py-2 text-gray-700">Gewinn / Verlust</td>
                        <td className="px-3 py-2 text-right" style={artDiv}>
                          <SignedAmount value={offerteSummeNum != null ? offerteSummeNum - summeOfferteKosten : null} />
                        </td>
                        {footerCalc(null)}
                        {footerCalc(<SignedAmount value={wvSummeNum != null ? wvSummeNum - summeWvKosten : null} />, pairDiv)}
                        {footerCalc(null)}
                        {footerCalc(<SignedAmount value={wvSummeNum != null ? wvSummeNum - summeWvKosten : null} />, pairDiv)}
                        {footerCalc(null)}
                        {footerErp(null, pairDiv)}
                        {footerErp(null)}
                      </tr>

                      {/* 3. Differenz zu vorherigem */}
                      <tr className="border-t border-gray-100">
                        <td className="px-6 py-2 text-gray-700">Differenz zu vorherigem</td>
                        <td className="px-3 py-2" style={artDiv} />
                        {footerCalc(null)}
                        {footerCalc(<SignedAmount value={deltaWvOff} />, pairDiv)}
                        {footerCalc(<SignedPctCell value={deltaWvOffPct} />)}
                        {footerCalc(
                          <SignedAmount value={deltaPlanWv === 0 ? 0 : deltaPlanWv} />,
                          pairDiv,
                        )}
                        {footerCalc(<SignedPctCell value={deltaPlanWvPct === 0 ? 0 : deltaPlanWvPct} />)}
                        {footerErp(<SignedAmount value={deltaIstPlan} polarity="pos-bad" withCurrency />, pairDiv)}
                        {footerErp(<SignedPctCell value={deltaIstPlanPct} polarity="pos-bad" />)}
                      </tr>

                      {/* 4. Bisher verr. Total */}
                      <tr className="border-t border-gray-100">
                        <td className="px-6 py-2 text-gray-700">Bisher verr. Total</td>
                        <td className="px-3 py-2" style={artDiv} />
                        {footerCalc(null)}
                        {footerCalc(null, pairDiv)}
                        {footerCalc(null)}
                        {footerCalc(null, pairDiv)}
                        {footerCalc(null)}
                        {footerErp(
                          <SignedAmount value={kennzahlen?.bisherVerrechnet?.value ?? null} />,
                          pairDiv,
                        )}
                        {footerErp(null)}
                      </tr>

                      {/* 5. Abgrenzung */}
                      <tr className="border-t border-gray-100">
                        <td className="px-6 py-2 text-gray-700">Abgrenzung</td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-400" style={artDiv}>–</td>
                        {footerCalc(null)}{footerCalc(null, pairDiv)}{footerCalc(null)}
                        {footerCalc(null, pairDiv)}{footerCalc(null)}
                        {footerErp(null, pairDiv)}{footerErp(null)}
                      </tr>

                      {/* 6. Vorrat */}
                      <tr className="border-t border-gray-100">
                        <td className="px-6 py-2 text-gray-700">Vorrat</td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-400" style={artDiv}>–</td>
                        {footerCalc(null)}{footerCalc(null, pairDiv)}{footerCalc(null)}
                        {footerCalc(null, pairDiv)}{footerCalc(null)}
                        {footerErp(null, pairDiv)}{footerErp(null)}
                      </tr>
                    </>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Visualisierung */}
          {showFinancials && <ProjectVisualization rows={vizRows} />}
        </>
      )}

      {!loading && !error && data && !p && (
        <p className="text-gray-500">Projekt nicht gefunden.</p>
      )}
    </Layout>
  );
}
