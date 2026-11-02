import { DEMO_NOTICE } from "../demo/demoData";

/** Shown on every screen: the prototype's results are samples, and nothing is booked. */
export function DemoBanner() {
  return (
    <div className="demo-banner" role="note" aria-label="Sample data notice">
      <strong>Sample data only.</strong> {DEMO_NOTICE} Real booking and payment are disabled.
    </div>
  );
}
