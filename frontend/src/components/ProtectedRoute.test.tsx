import { MemoryRouter, Route, Routes } from "react-router-dom";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProtectedRoute from "./ProtectedRoute";

const mockUser = {
  id: 1,
  username: "admin",
  capabilities: {
    canCreateProjekt: false,
    canManageStundensaetze: false,
    canViewFinanzen: true,
  },
};

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({ user: mockUser, loading: false, login: vi.fn(), logout: vi.fn() }),
}));

afterEach(cleanup);

function renderWithRoute(
  requiredCapability?: "canCreateProjekt" | "canManageStundensaetze" | "canViewFinanzen",
) {
  return render(
    <MemoryRouter initialEntries={["/geschuetzt"]}>
      <Routes>
        <Route
          path="/geschuetzt"
          element={
            <ProtectedRoute requiredCapability={requiredCapability}>
              <p>Inhalt</p>
            </ProtectedRoute>
          }
        />
        <Route path="/projekte" element={<p>Projektliste</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("zeigt Inhalt ohne requiredCapability", () => {
    renderWithRoute();
    expect(screen.getByText("Inhalt")).toBeInTheDocument();
  });

  it("leitet um, wenn die Capability fehlt", () => {
    renderWithRoute("canCreateProjekt");
    expect(screen.getByText("Projektliste")).toBeInTheDocument();
  });

  it("zeigt Inhalt, wenn die Capability vorhanden ist", () => {
    renderWithRoute("canViewFinanzen");
    expect(screen.getByText("Inhalt")).toBeInTheDocument();
  });
});
