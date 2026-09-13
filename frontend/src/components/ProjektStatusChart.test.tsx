import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ProjektStatusChart from "./ProjektStatusChart";

afterEach(cleanup);

describe("ProjektStatusChart", () => {
  it("zeigt Titel, die drei Linien und den offenen Betrag", () => {
    render(<ProjektStatusChart planWV={250000} sollWV={230000} ist={168400} ak={120000} />);
    expect(screen.getByText("Projektstatus auf einen Blick")).toBeInTheDocument();
    expect(screen.getByText("Plan-WV")).toBeInTheDocument();
    // "Ist-Kosten kum." und "AK verrechnet" stehen zweimal: Legende + Zeilen-Label.
    expect(screen.getAllByText("Ist-Kosten kum.")).toHaveLength(2);
    expect(screen.getAllByText("AK verrechnet")).toHaveLength(2);
    expect(screen.getByText("CHF 130'000.00")).toBeInTheDocument();
    expect(screen.getByText("52.0 % von Plan-WV")).toBeInTheDocument();
  });

  it("markiert Ist über Plan-WV", () => {
    render(<ProjektStatusChart planWV={250000} sollWV={230000} ist={290000} ak={120000} />);
    expect(screen.getByTestId("ist-wert")).toHaveTextContent("⚠");
    expect(
      screen.getByText("Ist-Kosten über Plan-WV: +CHF 40'000.00 (+16.0 %)"),
    ).toBeInTheDocument();
  });

  it("weist gedeckelte AK-Werte aus", () => {
    render(<ProjektStatusChart planWV={250000} sollWV={250000} ist={100} ak={260000} />);
    expect(screen.getByText("gedeckelt")).toBeInTheDocument();
    expect(screen.getByText("CHF 0.00")).toBeInTheDocument();
  });

  it("zeigt einen Hinweis ohne Plan-WV", () => {
    render(<ProjektStatusChart planWV={null} sollWV={null} ist={0} ak={0} />);
    expect(
      screen.getByText("Keine WV-Summe erfasst — Plan-WV fehlt."),
    ).toBeInTheDocument();
    // Ohne Plan-WV weder Legende noch Linien.
    expect(screen.queryAllByText("AK verrechnet")).toHaveLength(0);
  });
});
