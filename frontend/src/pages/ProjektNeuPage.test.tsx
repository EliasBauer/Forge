import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { describe, expect, it, vi } from "vitest";

import ProjektNeuPage from "./ProjektNeuPage";
import { PROJEKTLEITER } from "../graphql/queries";

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

describe("ProjektNeuPage", () => {
  it("befüllt das Projektleiter-Dropdown aus der PROJEKTLEITER-Query", async () => {
    render(
      <MemoryRouter>
        <MockedProvider mocks={[projektleiterMock]}>
          <ProjektNeuPage />
        </MockedProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText("anna")).toBeInTheDocument();
  });
});
