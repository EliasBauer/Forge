import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { chf, deDate } from "../utils/format";

export type RechnungRow = {
  id: string;
  dokumentNr: string;
  rechnungsdatum: string;
  firmenname: string;
  zeilenTitel: string | null;
  buchungskonto: { accountNo: string; name: string } | null;
  status: string;
  faelligkeitsdatum: string | null;
  ueberfaellig: boolean;
  betrag: number;
  steuerBerechnet: number;
  nettoBetrag: number;
};

type SortKey =
  | "rechnungsdatum"
  | "dokumentNr"
  | "firmenname"
  | "zeilenTitel"
  | "buchungskonto"
  | "status"
  | "faelligkeitsdatum"
  | "betrag"
  | "steuerBerechnet"
  | "nettoBetrag";

type Spalte = {
  key: SortKey;
  label: string;
  numerisch: boolean;
  rechts: boolean;
};

const SPALTEN: Spalte[] = [
  { key: "rechnungsdatum", label: "Datum", numerisch: false, rechts: false },
  { key: "dokumentNr", label: "Dokument-Nr", numerisch: false, rechts: false },
  { key: "firmenname", label: "Lieferant", numerisch: false, rechts: false },
  { key: "zeilenTitel", label: "Zeilentitel", numerisch: false, rechts: false },
  { key: "buchungskonto", label: "Buchungskonto", numerisch: false, rechts: false },
  { key: "status", label: "Status", numerisch: false, rechts: false },
  { key: "faelligkeitsdatum", label: "Fällig am", numerisch: false, rechts: false },
  { key: "betrag", label: "Brutto", numerisch: true, rechts: true },
  { key: "steuerBerechnet", label: "Steuer", numerisch: true, rechts: true },
  { key: "nettoBetrag", label: "Netto", numerisch: true, rechts: true },
];

function sortWert(row: RechnungRow, key: SortKey): string | number {
  if (key === "buchungskonto") return row.buchungskonto?.accountNo ?? "";
  const wert = row[key];
  if (wert == null) return "";
  return typeof wert === "number" ? wert : String(wert);
}

export default function RechnungenModal({
  title,
  rows,
  loading,
  error,
  onClose,
}: {
  title: string;
  rows: RechnungRow[];
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("rechnungsdatum");
  const [absteigend, setAbsteigend] = useState(true);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // aria-modal="true" verspricht, dass der Rest der Seite unerreichbar ist —
  // dafür muss der Fokus beim Öffnen aktiv auf den Dialog gelegt werden.
  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  function sortiereNach(spalte: Spalte) {
    if (spalte.key === sortKey) {
      setAbsteigend((a) => !a);
      return;
    }
    setSortKey(spalte.key);
    // Zahlen und Daten interessieren meist absteigend, Text aufsteigend.
    setAbsteigend(spalte.numerisch || spalte.key.includes("datum"));
  }

  const sortiert = [...rows].sort((a, b) => {
    const va = sortWert(a, sortKey);
    const vb = sortWert(b, sortKey);
    const cmp =
      typeof va === "number" && typeof vb === "number"
        ? va - vb
        : String(va).localeCompare(String(vb), "de");
    if (cmp !== 0) return absteigend ? -cmp : cmp;
    // Tiebreaker bleibt unabhängig von der Sortierrichtung stabil (nicht mitgedreht),
    // sonst sprängen gleichdatierte Zeilen beim Umkehren der Hauptsortierung.
    if (sortKey !== "dokumentNr") return a.dokumentNr.localeCompare(b.dokumentNr, "de");
    return 0;
  });

  const nettoSumme = rows.reduce((summe, r) => summe + r.nettoBetrag, 0);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="bg-white rounded-lg shadow-xl w-full max-w-[1100px] mt-10 focus:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold text-gray-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schliessen"
            className="p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {loading ? (
          <p className="px-6 py-8 text-sm text-gray-500">Lade Rechnungen…</p>
        ) : error ? (
          <p
            className="m-6 rounded-lg p-4 border text-sm"
            style={{
              color: "var(--forge-red)",
              borderColor: "var(--forge-red)",
              backgroundColor: "var(--forge-red-soft)",
            }}
          >
            {error}
          </p>
        ) : rows.length === 0 ? (
          <p className="px-6 py-8 text-sm text-gray-500">Keine Rechnungen</p>
        ) : (
          <>
            <div className="overflow-x-auto max-h-[70vh]">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b border-gray-200">
                    {SPALTEN.map((spalte) => (
                      <th
                        key={spalte.key}
                        className={`px-3 py-2.5 text-[11px] uppercase tracking-wider font-semibold text-gray-500 ${
                          spalte.rechts ? "text-right" : "text-left"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => sortiereNach(spalte)}
                          className="inline-flex items-center gap-1 hover:text-gray-900 transition-colors"
                        >
                          {spalte.label}
                          <span className="text-[9px]">
                            {sortKey === spalte.key ? (absteigend ? "▼" : "▲") : ""}
                          </span>
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody data-testid="rechnungen-body">
                  {sortiert.map((row) => (
                    <tr key={row.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/50">
                      <td className="px-3 py-2 text-gray-700 tabular-nums whitespace-nowrap">
                        {deDate(row.rechnungsdatum)}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-600">{row.dokumentNr}</td>
                      <td className="px-3 py-2 text-gray-800">{row.firmenname}</td>
                      <td className="px-3 py-2 text-gray-600">{row.zeilenTitel ?? "–"}</td>
                      <td className="px-3 py-2 text-gray-600 whitespace-nowrap">
                        {row.buchungskonto
                          ? `${row.buchungskonto.accountNo} ${row.buchungskonto.name}`
                          : "–"}
                      </td>
                      <td className="px-3 py-2 text-gray-600">{row.status}</td>
                      <td
                        data-testid={`faellig-${row.id}`}
                        className={`px-3 py-2 tabular-nums whitespace-nowrap ${
                          row.ueberfaellig ? "text-rose-700 font-medium" : "text-gray-600"
                        }`}
                      >
                        {row.ueberfaellig ? "⚠ " : ""}
                        {deDate(row.faelligkeitsdatum)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                        {chf(row.betrag, { withCurrency: false })}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                        {chf(row.steuerBerechnet, { withCurrency: false })}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium text-gray-900">
                        {chf(row.nettoBetrag, { withCurrency: false })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-6 py-3 border-t border-gray-100 text-[12px] text-gray-600 tabular-nums">
              {rows.length} {rows.length === 1 ? "Rechnung" : "Rechnungen"} · Netto{" "}
              {chf(nettoSumme)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
