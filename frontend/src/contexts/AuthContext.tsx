import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type UserGroup = "Admin" | "Projektleiter" | "Betrachter" | "Monteur";

export type AuthUser = {
  id: number;
  username: string;
  groups: UserGroup[];
  isStaff: boolean;
};

type AuthContextType = {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<string | null>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/me/")
      .then((r) => r.json())
      .then((data: AuthUser | null) => setUser(data))
      .finally(() => setLoading(false));
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
      setUser(data.user as AuthUser);
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
