import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ProjektKategorienChart, { type KategorieZeile } from "./ProjektKategorienChart";

afterEach(cleanup);

// Ist ueber Plan-WV (12'000 von 10'000) und Ist darunter (5'000 von 20'000).
// Gemeinsame Skala = 20'000, damit beide Zeilen vergleichbar bleiben.
const ZEILEN: KategorieZeile[] = [
  { schluessel: "apparate", label: "Apparate", planWV: 10000, ist: 12000 },
  { schluessel: "armaturen", label: "Armaturen", planWV: 20000, ist: 5000 },
];

describe("ProjektKategorienChart", () => {
  it("zeigt Titel, Legende und je Kategorie eine Zeile", () => {
    render(<ProjektKategorienChart rows={ZEILEN} />);
    expect(screen.getByText("Projektkategorien auf einen Blick")).toBeInTheDocument();
    expect(screen.getByText("Apparate")).toBeInTheDocument();
    expect(screen.getByText("Armaturen")).toBeInTheDocument();
    expect(screen.getByText("CHF 12'000.00")).toBeInTheDocument();
    expect(screen.getByText("Plan-WV CHF 10'000.00")).toBeInTheDocument();
    expect(screen.getByText("Überschreitung Plan-WV")).toBeInTheDocument();
  });

  it("skaliert alle Kategorien auf dieselbe Bezugsgrösse", () => {
    render(<ProjektKategorienChart rows={ZEILEN} />);
    // Die groesste Zahl im Chart ist Plan-WV von Armaturen (20'000) -> 100 %.
    expect(screen.getByTestId("kat-plan-armaturen")).toHaveStyle({ width: "100%" });
    expect(screen.getByTestId("kat-plan-apparate")).toHaveStyle({ width: "50%" });
  });

  it("setzt die rote Ist-Linie auf die Ist-Position", () => {
    render(<ProjektKategorienChart rows={ZEILEN} />);
    expect(screen.getByTestId("kat-ist-apparate")).toHaveStyle({ left: "60%" });
    expect(screen.getByTestId("kat-ist-armaturen")).toHaveStyle({ left: "25%" });
  });

  it("zeichnet die Überschreitung gestrichelt rot ab Plan-WV", () => {
    render(<ProjektKategorienChart rows={ZEILEN} />);
    const ueber = screen.getByTestId("kat-overrun-apparate");
    expect(ueber).toHaveStyle({ left: "50%", width: "10%" });
    // Ist unter Plan-WV bekommt keine Ueberschreitung.
    expect(screen.queryByTestId("kat-overrun-armaturen")).not.toBeInTheDocument();
  });

  it("zeigt Kategorien ohne Ist als noch offen und ohne Ist-Linie", () => {
    render(
      <ProjektKategorienChart
        rows={[{ schluessel: "planung", label: "Planung", planWV: 4000, ist: null }]}
      />,
    );
    expect(screen.getByText("noch offen")).toBeInTheDocument();
    expect(screen.queryByTestId("kat-ist-planung")).not.toBeInTheDocument();
    expect(screen.queryByTestId("kat-overrun-planung")).not.toBeInTheDocument();
  });

  it("rendert nichts, wenn keine Kategorie einen Wert hat", () => {
    const { container } = render(
      <ProjektKategorienChart
        rows={[{ schluessel: "planung", label: "Planung", planWV: null, ist: null }]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
