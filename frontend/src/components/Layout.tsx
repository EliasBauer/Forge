import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { canManageStundensaetze } from "../utils/permissions";

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `text-sm rounded-md px-3 py-1.5 transition-colors font-medium ${
      isActive
        ? "bg-blue-50"
        : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
    }`;

  const navLinkStyle = ({ isActive }: { isActive: boolean }) =>
    isActive ? { color: "var(--forge-blue)" } : {};

  return (
    <div className="min-h-screen" style={{ backgroundColor: "var(--forge-bg)" }}>
      <nav className="bg-white border-b border-gray-200 px-6 h-14 flex items-center gap-2 sticky top-0 z-10">
        <img src="/logo.svg" alt="Forge" className="h-7 w-auto mr-4" />

        {user && (
          <>
            <NavLink to="/projekte" className={navLinkClass} style={navLinkStyle}>
              Projekte
            </NavLink>
            {canManageStundensaetze(user) && (
              <NavLink to="/stundensaetze" className={navLinkClass} style={navLinkStyle}>
                Stundensätze
              </NavLink>
            )}
            <NavLink to="/aufgaben" className={navLinkClass} style={navLinkStyle}>
              Aufgaben
            </NavLink>
          </>
        )}

        {user && (
          <div className="ml-auto flex items-center gap-3">
            <span className="text-sm text-gray-600">{user.username}</span>
            <button
              type="button"
              onClick={handleLogout}
              className="text-sm text-gray-700 border border-gray-200 rounded-md px-3 py-1.5 hover:bg-gray-50 transition-colors"
            >
              Abmelden
            </button>
          </div>
        )}
      </nav>
      <main className="px-6 py-6 max-w-7xl mx-auto">{children}</main>
    </div>
  );
}
