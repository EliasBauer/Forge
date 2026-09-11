import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useApolloClient } from "@apollo/client/react";
import { ME } from "../graphql/queries";

export type AuthCapabilities = {
  canCreateProjekt: boolean;
  canManageStundensaetze: boolean;
  canViewFinanzen: boolean;
};

export type AuthUser = {
  id: number;
  username: string;
  capabilities: AuthCapabilities;
};

type MeQueryData = {
  me: { username: string; capabilities: AuthCapabilities };
};

type AuthContextType = {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<string | null>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | null>(null);

let nextClientSideId = 1;

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useApolloClient();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Gibt den geladenen User zurück (oder null), statt nur intern den State
  // zu setzen — login() nutzt den Rückgabewert, um einen fehlgeschlagenen
  // me-Query (REST-Login war erfolgreich, GraphQL-Query aber nicht) von
  // einem regulären "nicht eingeloggt" zu unterscheiden. Wirft NIE — ein
  // Netzwerkfehler/500/Schema-Mismatch degradiert auf "ausgeloggt", statt
  // login() bzw. den Mount-Effekt mit einer unhandled rejection hängen zu
  // lassen (der Login-Screen blieb sonst dauerhaft im Spinner-Zustand).
  async function refreshUser(): Promise<AuthUser | null> {
    try {
      const { data } = await client.query<MeQueryData>({
        query: ME,
        fetchPolicy: "network-only",
      });
      if (data?.me.username) {
        const nextUser: AuthUser = {
          id: nextClientSideId++,
          username: data.me.username,
          capabilities: data.me.capabilities,
        };
        setUser(nextUser);
        return nextUser;
      }
      setUser(null);
      return null;
    } catch {
      setUser(null);
      return null;
    }
  }

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(
    username: string,
    password: string,
  ): Promise<string | null> {
    const r = await fetch("/api/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await r.json();
    if (!data.success) {
      return (data.error as string) ?? "Anmeldung fehlgeschlagen.";
    }
    // Cache leeren, bevor der neue User geladen wird — sonst könnten hier
    // (Tab-übergreifender Re-Login als anderer User) noch Query-Ergebnisse
    // des vorherigen Users im InMemoryCache stehen.
    await client.clearStore();
    const nextUser = await refreshUser();
    if (!nextUser) {
      // REST-Login war erfolgreich, aber der me-Query ist gescheitert
      // (Netzwerkfehler/500/Schema-Mismatch) — nicht kommentarlos auf
      // "ausgeloggt" zurückfallen, sondern das der Nutzerin erklären.
      return "Anmeldung erfolgreich, aber Benutzerdaten konnten nicht geladen werden. Bitte Seite neu laden.";
    }
    return null;
  }

  async function logout(): Promise<void> {
    try {
      await fetch("/api/logout/", { method: "POST" });
    } catch {
      // Server-Logout best effort: ein Netzwerkfehler hier wird bewusst
      // verschluckt (kein Rethrow) — die Session-Cookie-Invalidierung auf
      // dem Server ist wünschenswert, aber das lokale Aufräumen unten muss
      // unabhängig davon laufen, siehe finally.
    } finally {
      // Läuft immer — auch wenn der Server-Logout fehlschlägt. Sonst bliebe
      // der User clientseitig "eingeloggt" und der Apollo-Cache mit seinen
      // Daten stehen.
      setUser(null);
      await client.clearStore();
    }
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth muss innerhalb von AuthProvider verwendet werden");
  return ctx;
}
