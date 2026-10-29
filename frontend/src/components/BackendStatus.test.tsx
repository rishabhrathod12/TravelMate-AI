import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { stubFetchResponse, stubHealthDown, stubHealthOk } from "../test/mockFetch";
import { BackendStatus } from "./BackendStatus";

describe("BackendStatus", () => {
  test("starts in a loading state", () => {
    stubHealthOk();

    render(<BackendStatus />);

    expect(screen.getByRole("status")).toHaveTextContent(/checking/i);
  });

  test("shows the real service name and version when the backend answers", async () => {
    stubHealthOk();

    render(<BackendStatus />);

    expect(await screen.findByText(/online · travelmate-ai v0\.1\.0/)).toBeInTheDocument();
  });

  test("says the backend is unreachable and offers a retry", async () => {
    stubHealthDown();

    render(<BackendStatus />);

    expect(await screen.findByText(/not reachable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  test("treats an unexpected response as offline instead of trusting it", async () => {
    stubFetchResponse({ status: "ok" });

    render(<BackendStatus />);

    expect(await screen.findByText(/not reachable/i)).toBeInTheDocument();
  });

  test("retry checks again and can recover", async () => {
    stubHealthDown();
    render(<BackendStatus />);
    await screen.findByText(/not reachable/i);

    stubHealthOk();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(/online · travelmate-ai/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
