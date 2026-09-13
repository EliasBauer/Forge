import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RechnungenModal, { type RechnungRow } from "./RechnungenModal";

afterEach(cleanup);

const rows: RechnungRow[] = [
  {
    id: "1",
    dokumentNr: "LR-100",
    rechnungsdatum: "2024-03-01",
    firmenname: "Beta AG",
    zeilenTitel: "Ventilator",
    buchungskonto: { accountNo: "4001", name: "Apparate" },
    status: "paid",
    faelligkeitsdatum: "2024-03-31",
    ueberfaellig: false,
    betrag: 1077,
    steuerBerechnet: 77,
    nettoBetrag: 1000,
  },
  {
    id: "2",
    dokumentNr: "LR-050",
    rechnungsdatum: "2024-01-15",
    firmenname: "Alpha GmbH",
    zeilenTitel: null,
    buchungskonto: null,
    status: "open",
    faelligkeitsdatum: "2024-02-15",
    ueberfaellig: true,
    betrag: 500,
    steuerBerechnet: 0,
    nettoBetrag: 500,
  },
];

function zeilenTexte(): string[] {
  const body = screen.getByTestId("rechnungen-body");
  return within(body)
    .getAllByRole("row")
    .map((row) => row.querySelectorAll("td")[1]?.textContent ?? "");
}

describe("RechnungenModal", () => {
  it("zeigt Titel, Zeilen und Fusszeile", () => {
    render(<RechnungenModal title="Rechnungen · Apparate" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    expect(screen.getByText("Rechnungen · Apparate")).toBeInTheDocument();
    expect(screen.getByText("LR-100")).toBeInTheDocument();
    expect(screen.getByText("4001 Apparate")).toBeInTheDocument();
    expect(screen.getByText("2 Rechnungen · Netto CHF 1'500.00")).toBeInTheDocument();
  });

  it("sortiert nach Datum absteigend als Standard", () => {
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    expect(zeilenTexte()).toEqual(["LR-100", "LR-050"]);
  });

  it("dreht die Sortierung beim Klick auf den Spaltenkopf", () => {
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Datum/ }));
    expect(zeilenTexte()).toEqual(["LR-050", "LR-100"]);
  });

  it("sortiert nach Lieferant aufsteigend", () => {
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Lieferant/ }));
    expect(zeilenTexte()).toEqual(["LR-050", "LR-100"]);
  });

  it("markiert überfällige Rechnungen", () => {
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    expect(screen.getByTestId("faellig-2")).toHaveTextContent("⚠");
  });

  it("schliesst per Button und per Escape", () => {
    const onClose = vi.fn();
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Schliessen" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("zeigt Lade- und Leerzustand", () => {
    const { rerender } = render(
      <RechnungenModal title="T" rows={[]} loading error={null} onClose={vi.fn()} />,
    );
    expect(screen.getByText("Lade Rechnungen…")).toBeInTheDocument();
    rerender(<RechnungenModal title="T" rows={[]} loading={false} error={null} onClose={vi.fn()} />);
    expect(screen.getByText("Keine Rechnungen")).toBeInTheDocument();
  });
});
