import { DEMO_NOTICE } from "../demo/demoData";

/** Shown on every screen: the prototype's results are samples, and nothing is booked. */
export function DemoBanner() {
  return (
    <div className="demo-banner" role="note" aria-label="Demo data notice">
      <strong>Prototype · demo data.</strong> {DEMO_NOTICE} Real booking and payment are
      disabled in this project.
    </div>
  );
}
