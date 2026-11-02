import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test } from "vitest";

import App from "./App";
import { stubHealthDown, stubHealthOk } from "./test/mockFetch";

beforeEach(() => {
  window.location.hash = "";
  stubHealthOk();
});

afterEach(() => {
  window.location.hash = "";
});

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "Menu" }));
}

describe("the application shell", () => {
  test("shows the TravelMate AI brand and keeps the links in a menu", () => {
    render(<App />);

    expect(screen.getByRole("link", { name: "TravelMate AI" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    openMenu();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toHaveTextContent("Plan Trip");
    expect(nav).toHaveTextContent("Trip Form");
    expect(nav).toHaveTextContent("My Trips");
    expect(nav).toHaveTextContent("About");
  });

  test("opens on the planning page and marks it as the current page", () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Where do you want to go?" })).toBeInTheDocument();
    openMenu();
    expect(screen.getByRole("link", { name: "Plan Trip" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "About" })).not.toHaveAttribute("aria-current");
    expect(document.title).toBe("Plan Trip · TravelMate AI");
  });

  test("the sample-data notice is always visible and says nothing is booked", () => {
    render(<App />);

    const notice = screen.getByRole("note", { name: "Sample data notice" });
    expect(notice).toHaveTextContent(/sample data/i);
    expect(notice).not.toHaveTextContent(/demo|prototype|mock/i);
    expect(notice).toHaveTextContent(/nothing is booked/i);
    expect(notice).toHaveTextContent(/booking and payment are disabled/i);
  });

  test("shows the real backend status", async () => {
    render(<App />);

    expect(await screen.findByText(/Backend: online · travelmate-ai v0\.1\.0/)).toBeInTheDocument();
  });

  test("still works when the backend is down", async () => {
    stubHealthDown();

    render(<App />);

    expect(await screen.findByText(/Backend: not reachable/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Where do you want to go?" })).toBeInTheDocument();
  });

  test("the skip link moves focus to the main content without changing the page", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("link", { name: "Skip to main content" }));

    expect(screen.getByRole("main")).toHaveFocus();
    expect(window.location.hash).toBe("");
  });
});

describe("the trip form", () => {
  test("is one menu entry away and keeps the home screen free of it", async () => {
    render(<App />);
    expect(screen.queryByRole("button", { name: /preview the trip/i })).not.toBeInTheDocument();

    openMenu();
    fireEvent.click(screen.getByRole("link", { name: "Trip Form" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Plan your trip" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview the trip" })).toBeInTheDocument();
    expect(document.title).toBe("Trip Form · TravelMate AI");
    expect(screen.getByRole("note", { name: "Sample data notice" })).toBeInTheDocument();
  });
});

describe("the menu", () => {
  test("closes with Escape and gives focus back to its button", () => {
    render(<App />);
    openMenu();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Menu" })).toHaveFocus();
  });
});

describe("navigation", () => {
  test("My Trips is an honest empty state", async () => {
    render(<App />);

    openMenu();
    fireEvent.click(screen.getByRole("link", { name: "My Trips" }));

    expect(await screen.findByRole("heading", { name: "My trips" })).toBeInTheDocument();
    expect(screen.getByText("No saved trips")).toBeInTheDocument();
    expect(screen.getByText(/Nothing is stored here/)).toBeInTheDocument();
    openMenu();
    expect(screen.getByRole("link", { name: "My Trips" })).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe("My Trips · TravelMate AI");
  });

  test("About says what exists, what is demo and what is not built", async () => {
    render(<App />);

    openMenu();
    fireEvent.click(screen.getByRole("link", { name: "About" }));

    expect(await screen.findByRole("heading", { name: "About TravelMate AI" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What exists today" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "About the sample data" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Not built yet" })).toBeInTheDocument();
    expect(screen.getByText(/Nothing in this app can book or pay/)).toBeInTheDocument();
  });

  test("the sample-data notice stays on every page", async () => {
    render(<App />);

    for (const name of ["My Trips", "About", "Plan Trip"]) {
      openMenu();
      fireEvent.click(screen.getByRole("link", { name }));
      await waitFor(() => expect(window.location.hash).not.toBe(""));
      expect(screen.getByRole("note", { name: "Sample data notice" })).toBeInTheDocument();
    }
  });

  test("moves focus to the page content after navigating", async () => {
    render(<App />);

    openMenu();
    fireEvent.click(screen.getByRole("link", { name: "About" }));
    await screen.findByRole("heading", { name: "About TravelMate AI" });

    expect(screen.getByRole("main")).toHaveFocus();
  });

  test("an unknown hash shows the planning page", () => {
    window.location.hash = "#/does-not-exist";

    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Where do you want to go?" })).toBeInTheDocument();
  });
});
