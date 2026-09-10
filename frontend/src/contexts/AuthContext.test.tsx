import { render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { gql } from "@apollo/client/core";
import { describe, expect, it } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";
import { ME } from "../graphql/queries";

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <p>lade</p>;
  return <p>{user ? `eingeloggt:${user.username}` : "ausgeloggt"}</p>;
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

describe("AuthContext", () => {
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
});
