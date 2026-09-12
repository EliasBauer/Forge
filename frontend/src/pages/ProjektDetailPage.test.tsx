import { MemoryRouter, Route, Routes } from "react-router-dom";
import { cleanup, render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProjektDetailPage from "./ProjektDetailPage";
import { GET_PROJEKT, GET_KOSTENART_IDS, GET_PROJEKT_STATUS_IDS, PROJEKTLEITER } from "../graphql/queries";
import { PROJEKT_DETAIL_SUBSCRIPTION } from "../graphql/subscriptions";

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "betrachter",
      capabilities: {
        canCreateProjekt: false,
        canManageStundensaetze: false,
        canViewFinanzen: true,
        canViewKostenPositionen: true,
      },
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

afterEach(cleanup);

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
          projektStatus: { id: "1", name: "Offen" },
          projektleiter: { id: "5", username: "anna" },
          capabilities,
          projektKennzahlenList: { items: [] },
          kostenPositionenList: { items: [] },
          istWertList: { items: [] },
        },
      },
    },
  };
}

const kostenartMock = {
  request: { query: GET_KOSTENART_IDS },
  result: { data: { kostenartList: { items: [] } } },
};
const statusMock = {
  request: { query: GET_PROJEKT_STATUS_IDS },
  result: { data: { projektStatusList: { items: [{ id: "1", name: "Offen" }] } } },
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

function renderPage(capabilities: { canUpdate: boolean; canDelete: boolean }) {
  return render(
    <MemoryRouter initialEntries={["/projekte/1"]}>
      <MockedProvider
        mocks={[projektMock(capabilities), kostenartMock, statusMock, subscriptionMock, projektleiterMock]}
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
