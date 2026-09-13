import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// @testing-library/react hängt sein Auto-Cleanup nur ein, wenn ein globales
// afterEach existiert — das gibt es hier nicht, weil vitest ohne `globals`
// läuft. Ohne Cleanup bleiben gerenderte Trees samt Apollo-Subscriptions
// montiert und committen nach dem jsdom-Teardown ("window is not defined").
afterEach(() => {
  cleanup();
});
