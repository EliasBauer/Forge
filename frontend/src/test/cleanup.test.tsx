import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

// Regression: Ohne globales `globals: true` registriert @testing-library/react
// sein Auto-Cleanup NICHT (es braucht ein globales afterEach). Montierte Trees
// überleben dann den Test, laufende Apollo-Subscriptions committen nach dem
// jsdom-Teardown und der Lauf bricht mit "window is not defined" ab.
// Diese Tests sichern, dass setup.ts das Cleanup selbst registriert.
const Marker = () => <div>cleanup-marker</div>;

describe("Test-Setup: Auto-Cleanup", () => {
  it("rendert den Marker einmal", () => {
    render(<Marker />);
    expect(screen.getAllByText("cleanup-marker")).toHaveLength(1);
  });

  it("startet mit leerem DOM, der vorige Tree ist unmountet", () => {
    render(<Marker />);
    expect(screen.getAllByText("cleanup-marker")).toHaveLength(1);
  });
});
