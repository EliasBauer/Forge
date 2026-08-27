import { MemoryRouter } from "react-router-dom";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { ApolloLink } from "@apollo/client/link";
import { getMainDefinition } from "@apollo/client/utilities";
import { MockLink, MockSubscriptionLink } from "@apollo/client/testing";
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

const listePage1Mock = {
  request: { query: GET_PROJEKTE, variables: { page: 1 } },
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

let intersectionCallback: (entries: Pick<IntersectionObserverEntry, "isIntersecting">[]) => void = () => {};

class FakeIntersectionObserver {
  constructor(callback: typeof intersectionCallback) {
    intersectionCallback = callback;
  }
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = () => [];
  root = null;
  rootMargin = "";
  thresholds: number[] = [];
}

// @ts-expect-error -- jsdom kennt IntersectionObserver nicht, Fake reicht für die Tests
global.IntersectionObserver = FakeIntersectionObserver;

function renderPage() {
  return render(
    <MemoryRouter>
      <MockedProvider mocks={[listePage1Mock, subscriptionMock]}>
        <ProjektListePage />
      </MockedProvider>
    </MemoryRouter>,
  );
}

function renderWithControlledSubscription(mocks: MockLink.MockedResponse[]) {
  const subscriptionLink = new MockSubscriptionLink();
  const queryLink = new MockLink(mocks, { showWarnings: false });
  const link = ApolloLink.split(
    ({ query }) => {
      const def = getMainDefinition(query);
      return def.kind === "OperationDefinition" && def.operation === "subscription";
    },
    subscriptionLink,
    queryLink,
  );
  const utils = render(
    <MemoryRouter>
      <MockedProvider link={link}>
        <ProjektListePage />
      </MockedProvider>
    </MemoryRouter>,
  );
  return { ...utils, subscriptionLink };
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

describe("ProjektListePage – Infinite Scroll", () => {
  it("lädt beim Erreichen des Sentinels die nächste Seite nach und hängt sie an", async () => {
    const page1 = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [
              projekt({ id: "1", auftragsnummer: "T-2026-003", name: "Projekt Eins" }),
              projekt({ id: "2", auftragsnummer: "T-2026-002", name: "Projekt Zwei" }),
            ],
            pageInfo: { totalCount: 3 },
          },
        },
      },
    };
    const page2 = {
      request: { query: GET_PROJEKTE, variables: { page: 2 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "3", auftragsnummer: "T-2026-001", name: "Projekt Drei" })],
            pageInfo: { totalCount: 3 },
          },
        },
      },
    };

    render(
      <MemoryRouter>
        <MockedProvider mocks={[page1, page2, subscriptionMock]}>
          <ProjektListePage />
        </MockedProvider>
      </MemoryRouter>,
    );

    await screen.findByText("Projekt Eins");
    expect(screen.queryByText("Projekt Drei")).not.toBeInTheDocument();

    intersectionCallback([{ isIntersecting: true }]);

    await screen.findByText("Projekt Drei");
    expect(screen.getByText("Projekt Eins")).toBeInTheDocument();
    expect(screen.getByText("Projekt Zwei")).toBeInTheDocument();
  });

  it("setzt bei einem Live-Update auf Seite 1 zurück und verwirft nachgeladene Seiten", async () => {
    const page1 = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "1", auftragsnummer: "T-2026-002", name: "Vor Update" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };
    const page2 = {
      request: { query: GET_PROJEKTE, variables: { page: 2 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "2", auftragsnummer: "T-2026-001", name: "Seite Zwei" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };
    const page1NachUpdate = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "3", auftragsnummer: "T-2026-003", name: "Nach Update" })],
            pageInfo: { totalCount: 1 },
          },
        },
      },
    };

    const { subscriptionLink } = renderWithControlledSubscription([page1, page2, page1NachUpdate]);

    await screen.findByText("Vor Update");
    intersectionCallback([{ isIntersecting: true }]);
    await screen.findByText("Seite Zwei");

    subscriptionLink.simulateResult({
      result: { data: { onProjektClassChange: { action: "updated" } } },
    });

    await screen.findByText("Nach Update");
    expect(screen.queryByText("Vor Update")).not.toBeInTheDocument();
    expect(screen.queryByText("Seite Zwei")).not.toBeInTheDocument();
  });

  it("verwirft eine noch ausstehende Seite-2-Antwort, wenn ein Live-Update dazwischenkommt", async () => {
    const page1 = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "1", auftragsnummer: "T-2026-002", name: "Reset Vorher" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };
    const page2Verspaetet = {
      request: { query: GET_PROJEKTE, variables: { page: 2 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "2", auftragsnummer: "T-2026-001", name: "Verspätete Seite Zwei" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
      delay: 300,
    };
    const page1NachUpdate = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "3", auftragsnummer: "T-2026-003", name: "Reset Nachher" })],
            pageInfo: { totalCount: 1 },
          },
        },
      },
    };

    const { subscriptionLink } = renderWithControlledSubscription([
      page1,
      page2Verspaetet,
      page1NachUpdate,
    ]);

    await screen.findByText("Reset Vorher");
    intersectionCallback([{ isIntersecting: true }]);

    // Live-Update kommt rein, WÄHREND die Seite-2-Antwort noch unterwegs ist (300ms delay).
    subscriptionLink.simulateResult({
      result: { data: { onProjektClassChange: { action: "updated" } } },
    });

    await screen.findByText("Reset Nachher");
    // Der verspäteten Seite-2-Antwort Zeit geben, aufzulösen — sie darf nicht mehr angehängt werden.
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(screen.queryByText("Verspätete Seite Zwei")).not.toBeInTheDocument();
    expect(screen.getByText("Reset Nachher")).toBeInTheDocument();
  });

  it("verwirft eine bereits laufende Seite-2-Antwort sofort beim Live-Update, auch wenn die neue Seite 1 verzögert eintrifft", async () => {
    const page1 = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "1", auftragsnummer: "T-2026-002", name: "Vorher Live" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };
    const page2Schnell = {
      request: { query: GET_PROJEKTE, variables: { page: 2 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "2", auftragsnummer: "T-2026-001", name: "Sollte nie erscheinen" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };
    const page1VerzoegertNachUpdate = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "3", auftragsnummer: "T-2026-003", name: "Verzögertes Reset-Ergebnis" })],
            pageInfo: { totalCount: 1 },
          },
        },
      },
      delay: 200,
    };

    const { subscriptionLink } = renderWithControlledSubscription([
      page1,
      page2Schnell,
      page1VerzoegertNachUpdate,
    ]);

    await screen.findByText("Vorher Live");
    intersectionCallback([{ isIntersecting: true }]);

    // Live-Update kommt sofort rein, WÄHREND die (schnelle) Seite-2-Antwort noch aussteht —
    // die neue Seite 1 (Reset) trifft aber erst mit 200ms Verzögerung ein.
    subscriptionLink.simulateResult({
      result: { data: { onProjektClassChange: { action: "updated" } } },
    });

    // Der schnellen Seite-2-Antwort Zeit geben aufzulösen, bevor die verzögerte Seite 1 da ist.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText("Sollte nie erscheinen")).not.toBeInTheDocument();

    await screen.findByText("Verzögertes Reset-Ergebnis");
    expect(screen.queryByText("Sollte nie erscheinen")).not.toBeInTheDocument();
  });
});

describe("ProjektListePage – Fehler beim Nachladen", () => {
  it("zeigt eine Wiederholungsaktion, die das Nachladen erneut auslöst", async () => {
    const page1 = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "1", auftragsnummer: "T-2026-002", name: "Retry Seite Eins" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };
    const page2Fehler = {
      request: { query: GET_PROJEKTE, variables: { page: 2 } },
      error: new Error("Netzwerkfehler"),
    };
    const page2Retry = {
      request: { query: GET_PROJEKTE, variables: { page: 2 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "2", auftragsnummer: "T-2026-001", name: "Retry Seite Zwei" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };

    render(
      <MemoryRouter>
        <MockedProvider mocks={[page1, page2Fehler, page2Retry, subscriptionMock]}>
          <ProjektListePage />
        </MockedProvider>
      </MemoryRouter>,
    );

    await screen.findByText("Retry Seite Eins");
    intersectionCallback([{ isIntersecting: true }]);

    const retryButton = await screen.findByRole("button", { name: /erneut versuchen/i });
    fireEvent.click(retryButton);

    await screen.findByText("Retry Seite Zwei");
  });
});
