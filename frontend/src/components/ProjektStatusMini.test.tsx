import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ProjektStatusMini from "./ProjektStatusMini";

afterEach(cleanup);

describe("ProjektStatusMini", () => {
  it("zeigt offenen Betrag und Prozent", () => {
    render(<ProjektStatusMini planWV={250000} sollWV={250000} ist={168400} ak={120000} />);
    expect(screen.getByTestId("mini-text")).toHaveTextContent("130'000 offen · 52 %");
  });

  it("faerbt den ganzen Text rot und haengt ein Warnzeichen an, wenn Ist ueber Plan-WV liegt", () => {
    render(<ProjektStatusMini planWV={250000} sollWV={250000} ist={290000} ak={120000} />);
    const text = screen.getByTestId("mini-text");
    expect(text).toHaveTextContent("130'000 offen · 52 % ⚠");
    expect(text.className).toContain("text-rose-700");
  });

  it("zeigt einen Hinweis ohne Plan-WV", () => {
    render(<ProjektStatusMini planWV={null} sollWV={null} ist={0} ak={0} />);
    expect(screen.getByText("keine WV-Summe")).toBeInTheDocument();
  });
});
