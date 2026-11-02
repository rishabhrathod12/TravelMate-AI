import { useEffect, useRef } from "react";

import { AppHeader } from "./components/AppHeader";
import { BackendStatus } from "./components/BackendStatus";
import { DemoBanner } from "./components/DemoBanner";
import { useRoute, type Route } from "./lib/route";
import { AboutView } from "./views/AboutView";
import { MyTripsView } from "./views/MyTripsView";
import { HomeView } from "./views/HomeView";

const PAGE_TITLE: Record<Route, string> = {
  plan: "Plan Trip",
  trips: "My Trips",
  about: "About",
};

export default function App() {
  const route = useRoute();
  const mainRef = useRef<HTMLElement>(null);
  const previousRoute = useRef(route);

  useEffect(() => {
    document.title = `${PAGE_TITLE[route]} · TravelMate AI`;
    // Move focus to the page content when the user navigates, not on first load.
    if (previousRoute.current !== route) {
      previousRoute.current = route;
      mainRef.current?.focus();
    }
  }, [route]);

  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#/plan"
        onClick={(event) => {
          // A plain "#main" link would change the hash and trigger navigation.
          event.preventDefault();
          mainRef.current?.focus();
        }}
      >
        Skip to main content
      </a>
      <AppHeader route={route} />
      <main
        id="main"
        className={route === "plan" ? "page page-home" : "page"}
        tabIndex={-1}
        ref={mainRef}
      >
        {/* The home screen is a voice button and a message box. Chat works only in development:
            it runs on a stand-in, and the backend refuses to serve it in production. */}
        {route === "plan" && <HomeView />}
        {route === "trips" && <MyTripsView />}
        {route === "about" && <AboutView />}
      </main>
      <footer className="app-footer">
        <DemoBanner />
        <BackendStatus />
      </footer>
    </div>
  );
}
