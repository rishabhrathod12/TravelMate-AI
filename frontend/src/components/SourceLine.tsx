import type { SourceMetadata } from "../contracts/types";
import { formatUtcDateTime } from "../lib/dates";
import { ProvenanceBadge } from "./Badges";

/** Provenance, provider and freshness of a provider-derived value. */
export function SourceLine({ source }: { source: SourceMetadata }) {
  const minutes = Math.round(source.freshness_window_seconds / 60);
  const isMock = source.provenance === "MOCK";
  return (
    <p className="source-line">
      <ProvenanceBadge provenance={source.provenance} />{" "}
      <span>
        Source: {source.provider_name} · retrieved {formatUtcDateTime(source.retrieved_at)}
        {isMock ? " (fictional demo timestamp)" : ""} · fresh for {minutes} min
      </span>
    </p>
  );
}
