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

  async function refreshUser(): Promise<void> {
    const { data } = await client.query<MeQueryData>({
      query: ME,
      fetchPolicy: "network-only",
    });
    if (data?.me.username) {
      setUser({
        id: nextClientSideId++,
        username: data.me.username,
        capabilities: data.me.capabilities,
      });
    } else {
      setUser(null);
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
    if (data.success) {
      await refreshUser();
      return null;
    }
    return (data.error as string) ?? "Anmeldung fehlgeschlagen.";
  }

  async function logout(): Promise<void> {
    await fetch("/api/logout/", { method: "POST" });
    setUser(null);
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
