import type { AvailabilityStatus, Provenance } from "../contracts/types";

const PROVENANCE_TEXT: Record<Provenance, { label: string; hint: string }> = {
  LIVE: { label: "LIVE", hint: "Fresh data from an authorised provider" },
  CACHED_LIVE: { label: "CACHED · may be stale", hint: "Provider data older than its freshness window" },
  MOCK: { label: "MOCK · demo data", hint: "Sample data. Not a real price or schedule" },
};

/** Says where a value came from. MOCK is never styled like LIVE. */
export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  const { label, hint } = PROVENANCE_TEXT[provenance];
  return (
    <span className={`badge badge-${provenance.toLowerCase().replace("_", "-")}`} title={hint}>
      <span className="visually-hidden">Data source:</span> {label}
    </span>
  );
}

const AVAILABILITY_TEXT: Record<AvailabilityStatus, { symbol: string; label: string }> = {
  AVAILABLE: { symbol: "✓", label: "Available" },
  UNAVAILABLE: { symbol: "✕", label: "Unavailable" },
  UNKNOWN: { symbol: "?", label: "Availability unknown" },
};

/** Text and a symbol, never colour alone. */
export function AvailabilityBadge({ availability }: { availability: AvailabilityStatus }) {
  const { symbol, label } = AVAILABILITY_TEXT[availability];
  return (
    <span className={`badge badge-${availability.toLowerCase()}`}>
      <span aria-hidden="true">{symbol} </span>
      {label}
    </span>
  );
}
