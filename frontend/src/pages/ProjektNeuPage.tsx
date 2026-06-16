import { useMutation } from "@apollo/client/react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { CREATE_PROJEKT } from "../graphql/mutations";

type MutationResult = {
  createProjekt: {
    success: boolean;
    Projekt: { id: string } | null;
  };
};

type UserOption = { id: number; username: string };

type FormState = {
  name: string;
  auftragsnummer: string;
  jahr: string;
  offerteSumme: string;
  wvSumme: string;
  projektleiter: string;
};

const inputClass =
  "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:border-transparent";

function parseCHF(raw: string): string | null {
  if (!raw.trim()) return null;
  const n = parseFloat(raw.replace(",", "."));
  if (isNaN(n) || n < 0) return null;
  return `${n.toFixed(2)} CHF`;
}

export default function ProjektNeuPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>({
    name: "",
    auftragsnummer: "",
    jahr: String(new Date().getFullYear()),
    offerteSumme: "",
    wvSumme: "",
    projektleiter: "",
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const [users, setUsers] = useState<UserOption[]>([]);

  useEffect(() => {
    fetch("/api/users/")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: UserOption[]) => setUsers(data))
      .catch(() => {});
  }, []);

  const [createProjekt, { loading }] = useMutation<MutationResult>(CREATE_PROJEKT, {
    refetchQueries: ["ProjektListe"],
    onCompleted(data) {
      if (data.createProjekt.success && data.createProjekt.Projekt) {
        navigate(`/projekte/${data.createProjekt.Projekt.id}`);
      } else {
        setServerError("Projekt konnte nicht erstellt werden.");
      }
    },
    onError(err) {
      setServerError(err.message);
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);
    const offerteSumme = parseCHF(form.offerteSumme);
    const wvSumme = parseCHF(form.wvSumme);
    const jahr = parseInt(form.jahr, 10);
    if (!offerteSumme) {
      setServerError("Bitte einen gültigen CHF-Betrag für die Offerte-Summe eingeben.");
      return;
    }
    if (form.wvSumme.trim() && !wvSumme) {
      setServerError("Bitte einen gültigen CHF-Betrag für die WV-Summe eingeben.");
      return;
    }
    if (isNaN(jahr) || jahr < 2000 || jahr > 2100) {
      setServerError("Bitte ein gültiges Jahr eingeben (2000–2100).");
      return;
    }
    createProjekt({
      variables: {
        name: form.name,
        auftragsnummer: form.auftragsnummer,
        jahr,
        offerteSumme,
        wvSumme: wvSumme ?? undefined,
        projektleiter: form.projektleiter || undefined,
      },
    });
  }

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) {
    const target = e.target;
    const value =
      target instanceof HTMLInputElement && target.type === "checkbox"
        ? target.checked
        : target.value;
    setForm((prev) => ({ ...prev, [target.name]: value }));
  }

  return (
    <Layout>
      <div className="mb-6">
        <Link
          to="/projekte"
          className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          ← Projekte
        </Link>
      </div>

      <div className="max-w-lg">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Neues Projekt</h1>

        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4"
        >
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
              Name *
            </label>
            <input
              id="name"
              name="name"
              type="text"
              required
              value={form.name}
              onChange={handleChange}
              className={inputClass}
              style={{ ["--tw-ring-color" as string]: "var(--forge-blue)" }}
              placeholder="Projekttitel"
            />
          </div>

          <div>
            <label
              htmlFor="auftragsnummer"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Auftragsnummer *
            </label>
            <input
              id="auftragsnummer"
              name="auftragsnummer"
              type="text"
              required
              value={form.auftragsnummer}
              onChange={handleChange}
              className={`${inputClass} font-mono`}
              placeholder="z. B. 2024-001"
            />
          </div>

          <div>
            <label htmlFor="jahr" className="block text-sm font-medium text-gray-700 mb-1">
              Jahr *
            </label>
            <input
              id="jahr"
              name="jahr"
              type="text"
              inputMode="numeric"
              required
              value={form.jahr}
              onChange={handleChange}
              className={inputClass}
              placeholder="z. B. 2024"
            />
          </div>

          <div>
            <label
              htmlFor="offerteSumme"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Offerte-Summe exkl. MwSt. (CHF) *
            </label>
            <input
              id="offerteSumme"
              name="offerteSumme"
              type="text"
              inputMode="decimal"
              required
              value={form.offerteSumme}
              onChange={handleChange}
              className={inputClass}
              placeholder="0.00"
            />
          </div>

          <div>
            <label
              htmlFor="wvSumme"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              WV-Summe exkl. MwSt. (CHF)
            </label>
            <input
              id="wvSumme"
              name="wvSumme"
              type="text"
              inputMode="decimal"
              value={form.wvSumme}
              onChange={handleChange}
              className={inputClass}
              placeholder="0.00 (optional)"
            />
          </div>

          <div>
            <label
              htmlFor="projektleiter"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Projektleiter
            </label>
            <select
              id="projektleiter"
              name="projektleiter"
              value={form.projektleiter}
              onChange={handleChange}
              className={`${inputClass} bg-white`}
              style={{ ["--tw-ring-color" as string]: "var(--forge-blue)" }}
            >
              <option value="">– kein Projektleiter –</option>
              {users.map((u) => (
                <option key={u.id} value={String(u.id)}>
                  {u.username}
                </option>
              ))}
            </select>
          </div>

          {serverError && (
            <p
              className="text-sm rounded-lg p-3 border"
              style={{
                color: "var(--forge-red)",
                borderColor: "var(--forge-red)",
                backgroundColor: "var(--forge-red-soft)",
              }}
            >
              {serverError}
            </p>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-lg text-sm font-medium text-white transition-colors disabled:opacity-50"
              style={{ backgroundColor: "var(--forge-blue)" }}
            >
              {loading ? "Speichern…" : "Projekt erstellen"}
            </button>
            <Link
              to="/projekte"
              className="px-5 py-2 rounded-lg text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors"
            >
              Abbrechen
            </Link>
          </div>
        </form>
      </div>
    </Layout>
  );
}
