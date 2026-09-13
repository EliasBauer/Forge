import { MemoryRouter, Route, Routes } from "react-router-dom";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProjektDetailPage from "./ProjektDetailPage";
import {
  GET_PROJEKT,
  GET_KOSTENART_IDS,
  GET_PROJEKT_PHASE_IDS,
  GET_PROJEKT_RECHNUNGEN,
  PROJEKTLEITER,
} from "../graphql/queries";
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

function renderPage(capabilities: { canUpdate: boolean; canDelete: boolean }) {
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

  it("öffnet alle Rechnungen über die Summenzeile", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    const summe = await screen.findByRole("button", { name: /950\.00/ });
    fireEvent.click(summe);
    expect(await screen.findByText("Alle Rechnungen · Testprojekt")).toBeInTheDocument();
  });
});
