import { MemoryRouter } from "react-router-dom";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { describe, expect, it, vi } from "vitest";

import ProjektListePage from "./ProjektListePage";
import { GET_PROJEKTE } from "../graphql/queries";
import { PROJEKT_LISTE_SUBSCRIPTION } from "../graphql/subscriptions";

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, username: "admin", groups: ["Admin"], isStaff: true },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

function projekt(overrides: Record<string, unknown> = {}) {
  return {
    id: "1",
    auftragsnummer: "T-2026-002",
    name: "Bauprojekt B",
    offerteSumme: { value: 10000, unit: "CHF" },
    wvSumme: { value: 9000, unit: "CHF" },
    auftragFertig: false,
    projektleiter: "Max Muster",
    projektKennzahlenList: {
      items: [{ summeWvPlus: { value: 9500, unit: "CHF" }, summeIstKosten: { value: 8000, unit: "CHF" } }],
    },
    ...overrides,
  };
}

const listeMock = {
  request: { query: GET_PROJEKTE },
  result: {
    data: {
      projektList: {
        items: [
          projekt({ id: "1", auftragsnummer: "T-2026-002", name: "Bauprojekt B" }),
          projekt({ id: "2", auftragsnummer: "T-2026-001", name: "Aufbauprojekt A" }),
        ],
        pageInfo: { totalCount: 2 },
      },
    },
  },
};

const subscriptionMock = {
  request: { query: PROJEKT_LISTE_SUBSCRIPTION },
  result: { data: { onProjektClassChange: { action: "noop" } } },
  delay: 1000 * 60 * 60,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <MockedProvider mocks={[listeMock, subscriptionMock]}>
        <ProjektListePage />
      </MockedProvider>
    </MemoryRouter>,
  );
}

describe("ProjektListePage – keine Client-Sortierung mehr", () => {
  it("Klick auf einen Spalten-Header ändert die Reihenfolge nicht", async () => {
    renderPage();
    await screen.findByText("Bauprojekt B");

    const rowsBefore = screen.getAllByRole("row").slice(1);
    expect(within(rowsBefore[0]).getByText("Bauprojekt B")).toBeInTheDocument();
    expect(within(rowsBefore[1]).getByText("Aufbauprojekt A")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Name"));

    const rowsAfter = screen.getAllByRole("row").slice(1);
    expect(within(rowsAfter[0]).getByText("Bauprojekt B")).toBeInTheDocument();
    expect(within(rowsAfter[1]).getByText("Aufbauprojekt A")).toBeInTheDocument();
  });

  it("zeigt die Summe im einheitlichen Format neben dem Suchfeld", async () => {
    renderPage();
    const total = await screen.findByText("2 von 2 Projekten");
    const searchInput = screen.getByPlaceholderText(/Suche nach Name/i);
    // eslint-disable-next-line no-bitwise
    expect(
      total.compareDocumentPosition(searchInput) & Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeTruthy();
  });
});
