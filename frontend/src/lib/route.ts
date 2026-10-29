import { useSyncExternalStore } from "react";

/** Hash-based navigation, so no router library is needed for three views. */

export type Route = "plan" | "trips" | "about";

export const ROUTES: readonly { route: Route; label: string; href: string }[] = [
  { route: "plan", label: "Plan Trip", href: "#/plan" },
  { route: "trips", label: "My Trips", href: "#/trips" },
  { route: "about", label: "About", href: "#/about" },
];

export function parseRoute(hash: string): Route {
  switch (hash) {
    case "#/trips":
      return "trips";
    case "#/about":
      return "about";
    default:
      return "plan";
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export function useRoute(): Route {
  return useSyncExternalStore(
    subscribe,
    () => parseRoute(window.location.hash),
    () => "plan",
  );
}
