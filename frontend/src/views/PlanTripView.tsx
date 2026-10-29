import { useEffect, useMemo, useRef, useState } from "react";

import { ApprovalPreview } from "../components/ApprovalPreview";
import { CostBreakdown } from "../components/CostBreakdown";
import { HeroArt } from "../components/HeroArt";
import { ItineraryView } from "../components/ItineraryView";
import { HotelCard, TransportCard } from "../components/OptionCards";
import { StatusMessage } from "../components/StatusMessage";
import { TripForm } from "../components/TripForm";
import type { TripRequest } from "../contracts/types";
import {
  buildDemoCostEstimate,
  buildDemoItinerary,
  buildDemoOptions,
  stayNights,
} from "../demo/demoData";
import { formatDay } from "../lib/dates";

function tripLabel(request: TripRequest): string {
  if (request.trip_type === "ONE_WAY") {
    return "One-way";
  }
  return request.return_date === request.departure_date ? "Same-day return" : "Round trip";
}

function showOption(optionId: string) {
  const element = document.getElementById(optionId);
  element?.focus();
  element?.scrollIntoView?.({ block: "center" });
}

export function PlanTripView() {
  const [request, setRequest] = useState<TripRequest | null>(null);
  const [transportId, setTransportId] = useState<string | null>(null);
  const [hotelId, setHotelId] = useState<string | null>(null);
  const resultsHeading = useRef<HTMLHeadingElement>(null);

  const demo = useMemo(() => (request === null ? null : buildDemoOptions(request)), [request]);

  useEffect(() => {
    if (request !== null) {
      resultsHeading.current?.focus();
    }
  }, [request]);

  function handleSubmit(next: TripRequest) {
    setRequest(next);
    setTransportId(null);
    setHotelId(null);
  }

  function clearSelection() {
    setTransportId(null);
    setHotelId(null);
  }

  const transport = demo?.transport.find((option) => option.id === transportId) ?? null;
  const hotel = demo?.hotels.find((option) => option.id === hotelId) ?? null;

  return (
    <>
      <section className="hero" aria-labelledby="plan-title">
        <div className="hero-copy">
          <h1 id="plan-title">Plan your trip</h1>
          <p>
            Describe a trip and preview how options, costs and a day-by-day plan will look. The
            results below are demo data until real providers are connected.
          </p>
        </div>
        <HeroArt />
      </section>

      <TripForm onSubmit={handleSubmit} />

      {request === null || demo === null ? (
        <StatusMessage kind="empty" title="No preview yet">
          Fill in the trip details, or use the example trip, then choose “Preview with demo data”.
        </StatusMessage>
      ) : (
        <div className="results">
          <h2 tabIndex={-1} ref={resultsHeading}>
            Demo results
          </h2>
          <p className="results-summary">
            {request.origin.name} to {request.destination.name} · {tripLabel(request)} · departs{" "}
            {formatDay(request.departure_date)}
            {request.return_date !== null && request.return_date !== request.departure_date
              ? `, returns ${formatDay(request.return_date)}`
              : ""}{" "}
            · {request.travellers.length}{" "}
            {request.travellers.length === 1 ? "traveller" : "travellers"}
          </p>

          <details className="request-preview">
            <summary>Request preview (JSON, not sent anywhere)</summary>
            <pre>{JSON.stringify(request, null, 2)}</pre>
          </details>

          <section aria-labelledby="transport-title">
            <h2 id="transport-title">Transport options (demo)</h2>
            {request.trip_type === "ROUND_TRIP" && (
              <p className="field-hint">Outbound options only. Return-leg options are not modelled in this prototype.</p>
            )}
            <div className="card-grid">
              {demo.transport.map((option) => (
                <TransportCard
                  key={option.id}
                  option={option}
                  quote={demo.quotes[option.id]}
                  selected={option.id === transportId}
                  onToggle={() => setTransportId(option.id === transportId ? null : option.id)}
                />
              ))}
            </div>
          </section>

          <section aria-labelledby="hotel-title">
            <h2 id="hotel-title">Hotel options (demo)</h2>
            {stayNights(request) < 1 && (
              <StatusMessage kind="info" title="Stay length is not defined for this trip">
                One-way and same-day trips have no defined hotel stay yet (open question Q13).
                Hotels are shown for reference, without a stay total.
              </StatusMessage>
            )}
            <div className="card-grid">
              {demo.hotels.map((option) => (
                <HotelCard
                  key={option.id}
                  option={option}
                  quote={demo.quotes[option.id]}
                  selected={option.id === hotelId}
                  onToggle={() => setHotelId(option.id === hotelId ? null : option.id)}
                />
              ))}
            </div>
          </section>

          <section aria-labelledby="cost-title">
            <h2 id="cost-title">Cost estimate (demo)</h2>
            {transport === null && hotel === null && (
              <StatusMessage kind="info" title="Nothing selected yet">
                Select a transport option and a hotel to add them to the estimate.
              </StatusMessage>
            )}
            <CostBreakdown
              estimate={buildDemoCostEstimate(request, transport, hotel, demo.quotes)}
            />
          </section>

          <section aria-labelledby="itinerary-title">
            <h2 id="itinerary-title">Sample itinerary</h2>
            <ItineraryView
              itinerary={buildDemoItinerary(request, transport, hotel)}
              departureDate={request.departure_date}
              optionNames={{
                ...(transport === null
                  ? {}
                  : { [transport.id]: `${transport.mode.toLowerCase()} to ${transport.destination.name}` }),
                ...(hotel === null ? {} : { [hotel.id]: hotel.name }),
              }}
              onShowOption={showOption}
            />
          </section>

          <section aria-labelledby="approval-title">
            <h2 id="approval-title">Booking approval preview</h2>
            {transport === null && hotel === null ? (
              <StatusMessage kind="empty" title="Nothing to preview">
                Select an option above to see what an approval screen will look like. Nothing can be
                booked.
              </StatusMessage>
            ) : (
              <ApprovalPreview
                transport={transport}
                hotel={hotel}
                quotes={demo.quotes}
                estimate={buildDemoCostEstimate(request, transport, hotel, demo.quotes)}
                onClear={clearSelection}
              />
            )}
          </section>
        </div>
      )}
    </>
  );
}
