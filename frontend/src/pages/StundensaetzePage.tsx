import { useMutation, useQuery } from "@apollo/client/react";
import { Clock, Trash2, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { CREATE_STUNDENSATZ, DELETE_STUNDENSATZ, UPDATE_STUNDENSATZ } from "../graphql/mutations";
import { GET_STUNDENSAETZE } from "../graphql/queries";
import { chf, type GQLMeasurement } from "../utils/format";

type Stundensatz = {
  id: string;
  jahr: number;
  stundensatz: GQLMeasurement;
};

type QueryData = {
  stundensatzList: { items: Stundensatz[]; pageInfo: { totalCount: number } };
};

type RateRow = { kind: "rate"; entry: Stundensatz };
type GapRow = { kind: "gap"; year: number };
type TableRow = RateRow | GapRow;

function buildRows(items: Stundensatz[]): TableRow[] {
  if (items.length === 0) return [];
  const sorted = [...items].sort((a, b) => b.jahr - a.jahr);
  const min = Math.min(...sorted.map((r) => r.jahr));
  const max = Math.max(...sorted.map((r) => r.jahr));
  const rows: TableRow[] = [];
  for (let y = max; y >= min; y--) {
    const found = sorted.find((r) => r.jahr === y);
    rows.push(found ? { kind: "rate", entry: found } : { kind: "gap", year: y });
  }
  return rows;
}

function parseCHF(raw: string): number | null {
  const n = parseFloat(raw.replace(/'/g, "").replace(",", "."));
  if (isNaN(n) || n <= 0) return null;
  return n;
}

function measurementStr(value: number): string {
  return `${value.toFixed(2)} CHF`;
}

export default function StundensaetzePage() {
  const { data, loading, error, refetch } = useQuery<QueryData>(GET_STUNDENSAETZE);

  const [inlineEdit, setInlineEdit] = useState<{ id: string; value: string } | null>(null);
  const [newRow, setNewRow] = useState<{ jahr: string; stundensatz: string } | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const escapeRef = useRef(false);

  const [createStundensatz, { loading: creating }] = useMutation(CREATE_STUNDENSATZ, {
    onCompleted() {
      setNewRow(null);
      setValidationError(null);
      refetch();
    },
    onError(err) {
      setMutationError(err.message);
    },
  });

  const [updateStundensatz] = useMutation(UPDATE_STUNDENSATZ, {
    onError(err) {
      setMutationError(err.message);
    },
    onCompleted() {
      refetch();
    },
  });

  const [deleteStundensatz] = useMutation(DELETE_STUNDENSATZ, {
    onCompleted() {
      refetch();
    },
    onError(err) {
      setMutationError(err.message);
    },
  });

  const items = data?.stundensatzList.items ?? [];
  const rows = buildRows(items);
  const gapCount = rows.filter((r) => r.kind === "gap").length;
  const maxJahr =
    items.length > 0 ? Math.max(...items.map((i) => i.jahr)) : new Date().getFullYear();

  function startNewRow(prefillYear?: number) {
    setNewRow({
      jahr: String(prefillYear ?? maxJahr + 1),
      stundensatz: "",
    });
    setValidationError(null);
    setMutationError(null);
    setInlineEdit(null);
  }

  function cancelNewRow() {
    setNewRow(null);
    setValidationError(null);
  }

  function saveNewRow() {
    if (!newRow) return;
    const jahrzahl = parseInt(newRow.jahr, 10);
    if (isNaN(jahrzahl) || jahrzahl < 2000 || jahrzahl > 2100) {
      setValidationError("Bitte ein gültiges Jahr eingeben.");
      return;
    }
    if (items.some((i) => i.jahr === jahrzahl)) {
      setValidationError(`Für ${jahrzahl} existiert bereits ein Stundensatz.`);
      return;
    }
    const rate = parseCHF(newRow.stundensatz);
    if (rate === null) {
      setValidationError("Bitte einen gültigen Betrag eingeben.");
      return;
    }
    setValidationError(null);
    createStundensatz({ variables: { jahr: jahrzahl, stundensatz: measurementStr(rate) } });
  }

  function startInlineEdit(entry: Stundensatz) {
    setInlineEdit({ id: entry.id, value: String(entry.stundensatz.value) });
    setMutationError(null);
    setNewRow(null);
  }

  function commitInlineEdit() {
    if (!inlineEdit) return;
    const rate = parseCHF(inlineEdit.value);
    if (rate === null) {
      setInlineEdit(null);
      return;
    }
    const id = parseInt(inlineEdit.id, 10);
    setInlineEdit(null);
    updateStundensatz({ variables: { id, stundensatz: measurementStr(rate) } });
  }

  function cancelInlineEdit() {
    setInlineEdit(null);
  }

  function handleInlineKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      commitInlineEdit();
    }
    if (e.key === "Escape") {
      escapeRef.current = true;
      cancelInlineEdit();
    }
  }

  function handleInlineBlur() {
    if (escapeRef.current) {
      escapeRef.current = false;
      return;
    }
    commitInlineEdit();
  }

  function handleNewRowKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") saveNewRow();
    if (e.key === "Escape") cancelNewRow();
  }

  function handleDelete(entry: Stundensatz) {
    setMutationError(null);
    deleteStundensatz({ variables: { id: parseInt(entry.id, 10) } });
  }

  const showEmpty = !loading && !error && items.length === 0 && newRow === null;
  const displayError = validationError ?? mutationError;

  const inputBase =
    "text-sm px-2 py-1.5 rounded focus:outline-none tabular-nums";
  const inlineInputClass =
    `${inputBase} border-2 border-blue-500 shadow-[0_0_0_3px_rgba(59,130,246,0.15)] w-24 text-right`;

  return (
    <Layout>
      {/* Header */}
      <div className="flex items-start justify-between mb-5 max-w-2xl">
        <div>
          <h1 className="text-[22px] font-semibold text-gray-900">Stundensätze</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {items.length > 0 && (
              <>
                {items.length} {items.length === 1 ? "Stundensatz" : "Stundensätze"}
                {gapCount > 0 && (
                  <span className="text-amber-600 ml-1">
                    · {gapCount} {gapCount === 1 ? "Jahr" : "Jahre"} ohne Satz
                  </span>
                )}
              </>
            )}
          </p>
        </div>
        {newRow === null && (
          <button
            type="button"
            onClick={() => startNewRow()}
            className="px-3.5 py-2 rounded-lg text-sm font-medium text-white transition-colors flex-shrink-0"
            style={{ backgroundColor: "var(--forge-blue)" }}
          >
            + Neuer Stundensatz
          </button>
        )}
      </div>

      {/* Error banner */}
      {displayError && (
        <div
          className="rounded-lg px-4 py-3 border text-sm mb-4 max-w-2xl"
          style={{
            color: "var(--forge-red)",
            borderColor: "var(--forge-red)",
            backgroundColor: "var(--forge-red-soft)",
          }}
        >
          {displayError}
        </div>
      )}

      {loading && <p className="text-sm text-gray-500">Lade Stundensätze…</p>}

      {error && !displayError && (
        <p
          className="rounded-lg p-4 border text-sm mb-4 max-w-2xl"
          style={{
            color: "var(--forge-red)",
            borderColor: "var(--forge-red)",
            backgroundColor: "var(--forge-red-soft)",
          }}
        >
          Fehler: {error.message}
        </p>
      )}

      {/* Empty state */}
      {showEmpty && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-12 flex flex-col items-center gap-3 max-w-2xl">
          <Clock className="w-16 h-16 text-gray-300" />
          <p className="text-[15px] font-semibold text-gray-700">Noch keine Stundensätze</p>
          <p className="text-sm text-gray-500 text-center">
            Erfasse den ersten Stundensatz, um Projektkosten berechnen zu können.
          </p>
          <button
            type="button"
            onClick={() => startNewRow()}
            className="mt-1 px-4 py-2 rounded-lg text-sm font-medium text-white transition-colors"
            style={{ backgroundColor: "var(--forge-blue)" }}
          >
            + Ersten Stundensatz anlegen
          </button>
        </div>
      )}

      {/* Table */}
      {(items.length > 0 || newRow !== null) && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden max-w-2xl">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-left">
                <th className="px-5 py-3 font-medium text-gray-600 w-[30%]">Jahr</th>
                <th className="px-5 py-3 font-medium text-gray-600 text-right w-[40%]">
                  CHF / Stunde
                </th>
                <th className="px-5 py-3 font-medium text-gray-600 w-[30%]" />
              </tr>
            </thead>
            <tbody>
              {/* New row */}
              {newRow !== null && (
                <tr className="border-b border-gray-100 bg-blue-50/60">
                  <td className="px-5 py-2.5">
                    <input
                      type="text"
                      inputMode="numeric"
                      value={newRow.jahr}
                      onChange={(e) =>
                        setNewRow((s) => (s ? { ...s, jahr: e.target.value } : s))
                      }
                      onKeyDown={handleNewRowKeyDown}
                      autoFocus
                      className={`${inputBase} border border-gray-300 w-20`}
                      placeholder="2025"
                    />
                  </td>
                  <td className="px-5 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <span className="text-gray-500">CHF</span>
                      <input
                        type="text"
                        inputMode="decimal"
                        value={newRow.stundensatz}
                        onChange={(e) =>
                          setNewRow((s) => (s ? { ...s, stundensatz: e.target.value } : s))
                        }
                        onKeyDown={handleNewRowKeyDown}
                        className={`${inputBase} border border-gray-300 w-24 text-right`}
                        placeholder="0.00"
                      />
                    </div>
                  </td>
                  <td className="px-5 py-2.5">
                    <div className="flex gap-2 justify-end">
                      <button
                        type="button"
                        onClick={saveNewRow}
                        disabled={creating}
                        className="text-xs px-3 py-1.5 rounded-md font-medium text-white disabled:opacity-50"
                        style={{ backgroundColor: "var(--forge-blue)" }}
                      >
                        {creating ? "…" : "Speichern"}
                      </button>
                      <button
                        type="button"
                        onClick={cancelNewRow}
                        className="text-xs px-3 py-1.5 rounded-md font-medium text-gray-600 bg-gray-100 hover:bg-gray-200"
                      >
                        Abbrechen
                      </button>
                    </div>
                  </td>
                </tr>
              )}

              {rows.map((row, idx) => {
                const isLast = idx === rows.length - 1;
                const borderClass = isLast ? "" : "border-b border-gray-100";

                if (row.kind === "gap") {
                  return (
                    <tr
                      key={`gap-${row.year}`}
                      className={`${borderClass} bg-amber-50/60 hover:bg-amber-50`}
                    >
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-1.5 text-amber-700 font-medium">
                          <TriangleAlert size={13} className="flex-shrink-0" />
                          {row.year}
                        </div>
                      </td>
                      <td className="px-5 py-3 text-right italic text-amber-700/80 text-[13px]">
                        kein Stundensatz hinterlegt
                      </td>
                      <td className="px-5 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => startNewRow(row.year)}
                          className="text-xs px-3 py-1 rounded-md font-medium text-amber-700 border border-amber-300 bg-white hover:bg-amber-50 transition-colors"
                        >
                          + Erfassen
                        </button>
                      </td>
                    </tr>
                  );
                }

                const entry = row.entry;
                const isEditing = inlineEdit?.id === entry.id;

                return (
                  <tr key={entry.id} className={`${borderClass} group`}>
                    <td className="px-5 py-3 text-gray-800 font-medium tabular-nums">
                      {entry.jahr}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {isEditing ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <span className="text-gray-500">CHF</span>
                          <input
                            type="text"
                            inputMode="decimal"
                            value={inlineEdit.value}
                            onChange={(e) =>
                              setInlineEdit((s) => (s ? { ...s, value: e.target.value } : s))
                            }
                            onKeyDown={handleInlineKeyDown}
                            onBlur={handleInlineBlur}
                            onFocus={(e) => e.target.select()}
                            autoFocus
                            className={inlineInputClass}
                          />
                        </div>
                      ) : (
                        <span className="text-gray-700 tabular-nums">
                          {chf(entry.stundensatz)}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {isEditing ? (
                          <button
                            type="button"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={commitInlineEdit}
                            className="text-xs px-3 py-1 rounded-md font-medium text-white"
                            style={{ backgroundColor: "var(--forge-blue)" }}
                          >
                            Fertig
                          </button>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => startInlineEdit(entry)}
                              disabled={inlineEdit !== null || newRow !== null}
                              className="text-xs px-3 py-1 rounded-md font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 disabled:opacity-40 transition-colors"
                            >
                              Bearbeiten
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDelete(entry)}
                              disabled={inlineEdit !== null || newRow !== null}
                              className="p-1.5 rounded-md text-gray-400 opacity-0 group-hover:opacity-100 hover:text-rose-600 hover:bg-rose-50 disabled:opacity-0 transition-all"
                              title="Löschen"
                            >
                              <Trash2 size={14} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Hint */}
      {items.length > 0 && gapCount > 0 && (
        <p className="mt-3 text-[12px] text-gray-400 max-w-2xl">
          Fehlende Stundensätze werden auch in{" "}
          <Link to="/aufgaben" className="underline hover:text-gray-600 transition-colors">
            Aufgaben
          </Link>{" "}
          angezeigt.
        </p>
      )}
    </Layout>
  );
}
