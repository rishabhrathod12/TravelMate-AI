import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import App from "./App";

test("renders the placeholder heading", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "TravelMate AI" })).toBeInTheDocument();
});
