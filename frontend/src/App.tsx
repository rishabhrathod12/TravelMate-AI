import { useEffect, useRef } from "react";

import { AppHeader } from "./components/AppHeader";
import { BackendStatus } from "./components/BackendStatus";
import { DemoBanner } from "./components/DemoBanner";
import { useRoute, type Route } from "./lib/route";
import { AboutView } from "./views/AboutView";
import { MyTripsView } from "./views/MyTripsView";
import { PlanTripView } from "./views/PlanTripView";

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
    <>
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
      <DemoBanner />
      <BackendStatus />
      <main id="main" className="page" tabIndex={-1} ref={mainRef}>
        {route === "plan" && <PlanTripView />}
        {route === "trips" && <MyTripsView />}
        {route === "about" && <AboutView />}
      </main>
      <footer className="app-footer">
        TravelMate AI · portfolio prototype · demo data only · nothing is booked
      </footer>
    </>
  );
}
