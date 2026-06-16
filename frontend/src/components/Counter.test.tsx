import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Counter } from "./Counter";

describe("Counter", () => {
  it("renders initial count and increments on click", () => {
    render(<Counter initial={5} />);

    expect(screen.getByLabelText("count")).toHaveTextContent("5");

    fireEvent.click(screen.getByRole("button", { name: /increment/i }));
    expect(screen.getByLabelText("count")).toHaveTextContent("6");
  });
});
