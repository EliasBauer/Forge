import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { describe, expect, it, vi } from "vitest";

import ProjektNeuPage from "./ProjektNeuPage";
import { GET_PROJEKT_STATUS_IDS, PROJEKTLEITER } from "../graphql/queries";

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "admin",
      capabilities: {
        canCreateProjekt: true,
        canManageStundensaetze: true,
        canViewFinanzen: true,
      },
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

const projektleiterMock = {
  request: { query: PROJEKTLEITER },
  result: {
    data: {
      benutzerList: {
        items: [{ id: "5", username: "anna" }],
      },
    },
  },
};

const projektStatusMock = {
  request: { query: GET_PROJEKT_STATUS_IDS },
  result: {
    data: {
      projektStatusList: {
        items: [
          { id: "1", name: "Offen" },
          { id: "2", name: "In Arbeit" },
          { id: "3", name: "Fertig" },
        ],
      },
    },
  },
};

describe("ProjektNeuPage", () => {
  it("befüllt das Projektleiter-Dropdown aus der PROJEKTLEITER-Query", async () => {
    render(
      <MemoryRouter>
        <MockedProvider mocks={[projektleiterMock, projektStatusMock]}>
          <ProjektNeuPage />
        </MockedProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText("anna")).toBeInTheDocument();
  });

  it("belegt den Status standardmässig mit 'Offen' vor", async () => {
    render(
      <MemoryRouter>
        <MockedProvider mocks={[projektleiterMock, projektStatusMock]}>
          <ProjektNeuPage />
        </MockedProvider>
      </MemoryRouter>,
    );
    const select = (await screen.findByLabelText(
      "Status *",
    )) as HTMLSelectElement;
    expect(await screen.findByText("Offen")).toBeInTheDocument();
    expect(select.value).toBe("1");
  });
});
