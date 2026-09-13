import { MemoryRouter, Route, Routes } from "react-router-dom";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { MockLink } from "@apollo/client/testing";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProjektDetailPage from "./ProjektDetailPage";
import {
  GET_PROJEKT,
  GET_KOSTENART_IDS,
  GET_PROJEKT_PHASE_IDS,
  GET_PROJEKT_RECHNUNGEN,
  PROJEKTLEITER,
} from "../graphql/queries";
import { UPDATE_PROJEKT } from "../graphql/mutations";
import { PROJEKT_DETAIL_SUBSCRIPTION } from "../graphql/subscriptions";

const { mockCapabilities } = vi.hoisted(() => ({
  mockCapabilities: {
    canCreateProjekt: false,
    canManageStundensaetze: false,
    canViewFinanzen: true,
    canViewKostenPositionen: true,
  },
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "betrachter",
      capabilities: mockCapabilities,
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  mockCapabilities.canViewFinanzen = true;
  mockCapabilities.canViewKostenPositionen = true;
});

function projektMock(capabilities: { canUpdate: boolean; canDelete: boolean }) {
  return {
    request: { query: GET_PROJEKT, variables: { id: "1" } },
    result: {
      data: {
        projekt: {
          id: "1",
          name: "Testprojekt",
          auftragsnummer: "T-1",
          jahr: 2026,
          offerteSumme: { value: 1000, unit: "CHF" },
          wvSumme: null,
          projektPhase: { id: "1", name: "Offen" },
          projektleiter: { id: "5", username: "anna" },
          capabilities,
          projektKennzahlenList: {
            items: [
              {
                summeOfferteKosten: { value: 500, unit: "CHF" },
                summeWvKosten: { value: 450, unit: "CHF" },
                summeIstKosten: { value: 950, unit: "CHF" },
                verbrauchsrate: 80,
                deltaWvOff: { value: -50, unit: "CHF" },
                deltaWvOffPct: -10,
                deltaIstPlan: { value: -50, unit: "CHF" },
                deltaIstPlanPct: -11.1,
                summeWvPlus: { value: 450, unit: "CHF" },
                bisherVerrechnet: { value: -950, unit: "CHF" },
              },
            ],
          },
          kostenPositionenList: {
            items: [
              {
                id: "10",
                art: { schluessel: "apparate" },
                offerteKostenWert: { value: 500, unit: "CHF" },
                offerteStunden: null,
                wvKostenWert: { value: 450, unit: "CHF" },
                wvKostenWertProzent: 100,
                offerteKostenWertProzent: 100,
              },
            ],
          },
          istWertList: {
            items: [
              {
                kostenart: { schluessel: "apparate" },
                istKostenWert: { value: 400, unit: "CHF" },
                istKostenWertProzent: 100,
              },
            ],
          },
        },
      },
    },
  };
}

const kostenartMock = {
  request: { query: GET_KOSTENART_IDS },
  result: { data: { kostenartList: { items: [] } } },
};
const phaseMock = {
  request: { query: GET_PROJEKT_PHASE_IDS },
  result: { data: { projektPhaseList: { items: [{ id: "1", name: "Offen" }] } } },
};
const subscriptionMock = {
  request: { query: PROJEKT_DETAIL_SUBSCRIPTION, variables: { id: "1" } },
  result: { data: { onProjektChange: { action: "noop" } } },
  delay: 1000 * 60 * 60,
};
const projektleiterMock = {
  request: { query: PROJEKTLEITER },
  result: { data: { benutzerList: { items: [{ id: "5", username: "anna" }] } } },
};
const rechnungenMock = {
  request: { query: GET_PROJEKT_RECHNUNGEN, variables: { id: "1" } },
  result: {
    data: {
      projekt: {
        id: "1",
        projektKennzahlenList: { items: [{ rechnungen: [] }] },
        istWertList: {
          items: [
            {
              kostenart: { schluessel: "apparate" },
              rechnungen: [
                {
                  id: "7",
                  dokumentNr: "LR-777",
                  rechnungsdatum: "2024-05-02",
                  firmenname: "Muster AG",
                  zeilenTitel: "Lüfter",
                  status: "paid",
                  faelligkeitsdatum: "2024-06-01",
                  ueberfaellig: false,
                  betrag: 1077,
                  steuerBerechnet: 77,
                  nettoBetrag: 1000,
                  buchungskonto: { accountNo: "4001", name: "Apparate" },
                },
              ],
            },
          ],
        },
      },
    },
  },
};

function renderPage(
  capabilities: { canUpdate: boolean; canDelete: boolean },
  extraMocks: MockLink.MockedResponse[] = [],
) {
  return render(
    <MemoryRouter initialEntries={["/projekte/1"]}>
      <MockedProvider
        mocks={[
          projektMock(capabilities),
          kostenartMock,
          phaseMock,
          subscriptionMock,
          projektleiterMock,
          rechnungenMock,
          ...(extraMocks ?? []),
        ]}
      >
        <Routes>
          <Route path="/projekte/:id" element={<ProjektDetailPage />} />
        </Routes>
      </MockedProvider>
    </MemoryRouter>,
  );
}

describe("ProjektDetailPage – Bearbeiten-Button folgt projekt.capabilities.canUpdate", () => {
  it("zeigt den Bearbeiten-Button, wenn canUpdate true ist", async () => {
    renderPage({ canUpdate: true, canDelete: true });
    expect(await screen.findByText("Bearbeiten")).toBeInTheDocument();
  });

  it("versteckt den Bearbeiten-Button, wenn canUpdate false ist", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");
    expect(screen.queryByText("Bearbeiten")).not.toBeInTheDocument();
  });
});

describe("ProjektDetailPage – Kopf speichern", () => {
  // GM >= 0.80.1 lässt weggelassene Mutation-Argumente unverändert. Ein geleertes
  // Feld muss deshalb explizit `null` senden, sonst bleibt der alte Wert stehen.
  it("sendet für geleerte optionale Felder explizit null", async () => {
    const updateMock = {
      request: {
        query: UPDATE_PROJEKT,
        variables: {
          id: "1",
          name: "Testprojekt",
          offerteSumme: "1000.00 CHF",
          wvSumme: null,
          projektleiter: null,
          projektPhase: "1",
        },
      },
      result: { data: { updateProjekt: { success: true } } },
    };
    const capabilities = { canUpdate: true, canDelete: true };
    // Zweiter Projekt-Mock für das refetch() nach erfolgreichem Speichern.
    renderPage(capabilities, [updateMock, projektMock(capabilities)]);
    fireEvent.click(await screen.findByText("Bearbeiten"));
    const projektleiterSelect = await screen.findByDisplayValue("anna");
    fireEvent.change(projektleiterSelect, { target: { value: "" } });
    fireEvent.click(screen.getByText("Speichern"));
    // Erst nach erfolgreicher Mutation verlässt die Seite den Bearbeiten-Modus.
    expect(await screen.findByText("Bearbeiten")).toBeInTheDocument();
    expect(screen.queryByText(/fehlgeschlagen|No more mocked/)).not.toBeInTheDocument();
  });
});

describe("ProjektDetailPage – Positionszeilen folgen canViewKostenPositionen", () => {
  it("zeigt Positionszeilen, Legende und Diagramm, wenn die Capability gesetzt ist", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");

    // "Apparate" erscheint bewusst zweimal (Tabellenzeile + Diagrammbalken),
    // wenn Positionen sichtbar sind — daher auf die Tabelle eingegrenzt.
    expect(within(screen.getByRole("table")).getByText("Apparate")).toBeInTheDocument();
    expect(screen.getByText("berechnet")).toBeInTheDocument();
    expect(screen.getByText("Projektstatus auf einen Blick")).toBeInTheDocument();
  });

  it("versteckt Positionszeilen, Legende und Diagramm ohne die Capability", async () => {
    mockCapabilities.canViewKostenPositionen = false;
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");

    expect(screen.queryByText("Apparate")).not.toBeInTheDocument();
    expect(screen.queryByText("berechnet")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Projektstatus auf einen Blick"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Projektkategorien auf einen Blick"),
    ).not.toBeInTheDocument();
  });

  it("zeigt Header-Summen und den Footer auch ohne Positionszeilen", async () => {
    mockCapabilities.canViewKostenPositionen = false;
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");

    expect(screen.getByText("Offerte exkl. MwSt.")).toBeInTheDocument();
    expect(screen.getByText("WV-Summe exkl. MwSt.")).toBeInTheDocument();
    expect(screen.getByText("Summe der Kosten")).toBeInTheDocument();
    expect(screen.getByText("Gewinn / Verlust")).toBeInTheDocument();
  });

  it("zeigt die Summen-Ist-Zelle ohne die Capability als reinen Text, nicht als Button", async () => {
    mockCapabilities.canViewKostenPositionen = false;
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");

    expect(screen.queryByRole("button", { name: /950\.00/ })).not.toBeInTheDocument();
    expect(screen.getByText("CHF 950.00")).toBeInTheDocument();
  });
});

describe("ProjektDetailPage – Visualisierungskarten", () => {
  it("zeigt beide Karten mit ihren Titeln", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    expect(
      await screen.findByText("Projektstatus auf einen Blick"),
    ).toBeInTheDocument();
    expect(screen.getByText("Projektkategorien auf einen Blick")).toBeInTheDocument();
  });

  it("nennt die erste Wertspalte Offerte", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    expect(await screen.findByText("Offerte")).toBeInTheDocument();
    expect(screen.queryByText("Soll-Offerte")).not.toBeInTheDocument();
  });
});

describe("ProjektDetailPage – Rechnungen-Pop-up", () => {
  it("öffnet das Rechnungen-Pop-up beim Klick auf einen Ist-Wert", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    const istZelle = await screen.findByRole("button", { name: /400\.00/ });
    fireEvent.click(istZelle);
    expect(await screen.findByText("LR-777")).toBeInTheDocument();
    expect(screen.getByText("Rechnungen · Apparate")).toBeInTheDocument();
  });

  it("macht eine Ist-Zelle ohne Wert nicht klickbar", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    // "Kanäle und Rohre" hat weder kostenPosition noch istWert im Mock — die
    // Ist-Zelle zeigt "–" und darf keinen Button (Rechnungen-Pop-up) enthalten.
    const zeile = (await screen.findByText("Kanäle und Rohre")).closest("tr") as HTMLElement;
    expect(within(zeile).queryByRole("button")).not.toBeInTheDocument();
  });

  it("öffnet alle Rechnungen über die Summenzeile", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    const summe = await screen.findByRole("button", { name: /950\.00/ });
    fireEvent.click(summe);
    expect(await screen.findByText("Alle Rechnungen · Testprojekt")).toBeInTheDocument();
  });

  it("lädt bei jedem Öffnen neu, statt den letzten Stand zu behalten", async () => {
    // Zweiter GET_PROJEKT_RECHNUNGEN-Mock mit anderem Inhalt: erscheint er nach
    // dem zweiten Öffnen, wurde tatsächlich neu geladen statt der alte Stand
    // aus dem ersten Fetch weiterverwendet.
    const rechnungenMockNeu = {
      request: { query: GET_PROJEKT_RECHNUNGEN, variables: { id: "1" } },
      result: {
        data: {
          projekt: {
            id: "1",
            projektKennzahlenList: { items: [{ rechnungen: [] }] },
            istWertList: {
              items: [
                {
                  kostenart: { schluessel: "apparate" },
                  rechnungen: [
                    {
                      id: "9",
                      dokumentNr: "LR-999",
                      rechnungsdatum: "2024-07-01",
                      firmenname: "Neu AG",
                      zeilenTitel: null,
                      status: "open",
                      faelligkeitsdatum: null,
                      ueberfaellig: false,
                      betrag: 500,
                      steuerBerechnet: 0,
                      nettoBetrag: 500,
                      buchungskonto: null,
                    },
                  ],
                },
              ],
            },
          },
        },
      },
    };

    render(
      <MemoryRouter initialEntries={["/projekte/1"]}>
        <MockedProvider
          mocks={[
            projektMock({ canUpdate: false, canDelete: false }),
            kostenartMock,
            phaseMock,
            subscriptionMock,
            projektleiterMock,
            rechnungenMock,
            rechnungenMockNeu,
          ]}
        >
          <Routes>
            <Route path="/projekte/:id" element={<ProjektDetailPage />} />
          </Routes>
        </MockedProvider>
      </MemoryRouter>,
    );

    const istZelle = await screen.findByRole("button", { name: /400\.00/ });
    fireEvent.click(istZelle);
    expect(await screen.findByText("LR-777")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Schliessen" }));

    fireEvent.click(screen.getByRole("button", { name: /400\.00/ }));
    expect(await screen.findByText("LR-999")).toBeInTheDocument();
    expect(screen.queryByText("LR-777")).not.toBeInTheDocument();
  });
});

describe("ProjektDetailPage – Kopfzeile", () => {
  it("zeigt die Auftragsnummer ohne technische ID", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    // Die ID steht schon in der URL; in der Kopfzeile hilft sie niemandem.
    expect(await screen.findByText("T-1")).toBeInTheDocument();
    expect(screen.queryByText(/\(id:/)).not.toBeInTheDocument();
  });

  it("legt die sechs Kennzahlen des Kopfs auf eine Zeile", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    const grid = await screen.findByTestId("projekt-kopf-grid");
    expect(grid.children).toHaveLength(6);
    expect(grid).toHaveClass("lg:grid-cols-6");
  });
});
