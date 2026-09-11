import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { ApolloClient } from "@apollo/client";
import { gql } from "@apollo/client/core";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";
import { ME } from "../graphql/queries";

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <p>lade</p>;
  return <p>{user ? `eingeloggt:${user.username}` : "ausgeloggt"}</p>;
}

function ProbeMitLogout() {
  const { user, loading, logout } = useAuth();
  const [warning, setWarning] = useState<string | null>(null);
  return (
    <div>
      <p>{loading ? "lade" : user ? `eingeloggt:${user.username}` : "ausgeloggt"}</p>
      <button
        onClick={() => {
          void logout().then(setWarning);
        }}
      >
        logout
      </button>
      {warning && <p>logoutWarning:{warning}</p>}
    </div>
  );
}

const meAdminMock = {
  request: { query: ME },
  result: {
    data: {
      me: {
        username: "admin",
        capabilities: {
          canCreateProjekt: true,
          canManageStundensaetze: true,
          canViewFinanzen: true,
        },
      },
    },
  },
};

const meAnonymMock = {
  request: { query: ME },
  result: {
    data: {
      me: {
        username: "",
        capabilities: {
          canCreateProjekt: false,
          canManageStundensaetze: false,
          canViewFinanzen: false,
        },
      },
    },
  },
};

const meErrorMock = {
  request: { query: ME },
  error: new Error("Netzwerkfehler beim me-Query"),
};

describe("AuthContext", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("setzt user bei nichtleerem username", async () => {
    render(
      <MockedProvider mocks={[meAdminMock]}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MockedProvider>,
    );
    await waitFor(() => screen.getByText("eingeloggt:admin"));
  });

  it("bleibt user null bei leerem username (nicht eingeloggt)", async () => {
    render(
      <MockedProvider mocks={[meAnonymMock]}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MockedProvider>,
    );
    await waitFor(() => screen.getByText("ausgeloggt"));
  });

  it("löst loading trotz fehlgeschlagenem me-Query auf und bleibt nicht hängen", async () => {
    render(
      <MockedProvider mocks={[meErrorMock]}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MockedProvider>,
    );
    // "lade" darf nicht dauerhaft stehen bleiben (Finding: hängender
    // Login-Screen bei fehlgeschlagenem me-Query) — refreshUser() fängt
    // den Fehler jetzt ab und setzt user auf null.
    await waitFor(() => screen.getByText("ausgeloggt"));
    expect(screen.queryByText("lade")).not.toBeInTheDocument();
  });

  it("ruft client.clearStore() beim Logout auf (Cross-User-Cache-Leak-Schutz)", async () => {
    const clearStoreSpy = vi.spyOn(ApolloClient.prototype, "clearStore");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MockedProvider mocks={[meAdminMock]}>
        <AuthProvider>
          <ProbeMitLogout />
        </AuthProvider>
      </MockedProvider>,
    );
    await waitFor(() => screen.getByText("eingeloggt:admin"));

    screen.getByText("logout").click();

    await waitFor(() => screen.getByText("ausgeloggt"));
    expect(fetchMock).toHaveBeenCalledWith("/api/logout/", { method: "POST" });
    expect(clearStoreSpy).toHaveBeenCalled();
    // Server hat mit 2xx bestätigt — logout() meldet keine Warnung zurück.
    expect(screen.queryByText(/^logoutWarning:/)).not.toBeInTheDocument();
  });

  it("räumt lokal auf und meldet eine Warnung, wenn der Server-Logout-Request fehlschlägt (Netzwerkfehler)", async () => {
    const clearStoreSpy = vi.spyOn(ApolloClient.prototype, "clearStore");
    const fetchMock = vi.fn().mockRejectedValue(new Error("Netzwerkfehler"));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MockedProvider mocks={[meAdminMock]}>
        <AuthProvider>
          <ProbeMitLogout />
        </AuthProvider>
      </MockedProvider>,
    );
    await waitFor(() => screen.getByText("eingeloggt:admin"));

    screen.getByText("logout").click();

    // Der Server-Request schlägt fehl, aber user/Cache müssen trotzdem
    // bereinigt werden (Finding: logout() ließ bei fehlschlagendem fetch
    // sowohl setUser(null) als auch clearStore() aus) — UND der Aufrufer
    // muss erfahren, dass die Abmeldung serverseitig unbestätigt blieb.
    await waitFor(() => screen.getByText("ausgeloggt"));
    expect(clearStoreSpy).toHaveBeenCalled();
    await waitFor(() => screen.getByText(/^logoutWarning:/));
  });

  it("räumt lokal auf und meldet eine Warnung, wenn der Server-Logout eine Nicht-2xx-Antwort liefert", async () => {
    const clearStoreSpy = vi.spyOn(ApolloClient.prototype, "clearStore");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MockedProvider mocks={[meAdminMock]}>
        <AuthProvider>
          <ProbeMitLogout />
        </AuthProvider>
      </MockedProvider>,
    );
    await waitFor(() => screen.getByText("eingeloggt:admin"));

    screen.getByText("logout").click();

    // Der Server antwortet (kein Netzwerkfehler), aber mit einem
    // Fehlerstatus — response.ok muss geprüft werden, nicht nur, ob fetch()
    // resolved (Finding: bisher wurde nur ein rejected Promise erkannt,
    // eine 4xx/5xx-Antwort lief unbemerkt durch).
    await waitFor(() => screen.getByText("ausgeloggt"));
    expect(clearStoreSpy).toHaveBeenCalled();
    await waitFor(() => screen.getByText(/^logoutWarning:/));
  });
});
