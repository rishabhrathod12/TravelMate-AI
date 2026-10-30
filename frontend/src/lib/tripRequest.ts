import type { TripRequest } from "../contracts/types";
import { isValidIsoDate } from "./dates";

/**
 * Form values and validation for a trip request.
 *
 * The rules copy `backend/app/domain/trip.py`: a one-way trip has no return
 * date, a round trip needs one on or after departure, and a same-day return is a
 * round trip with the same date. They are copied by hand and can drift until the
 * generated API client arrives (Milestone 8).
 */

export type TripKind = "ONE_WAY" | "ROUND_TRIP" | "SAME_DAY_RETURN";

export interface TripFormValues {
  origin: string;
  destination: string;
  tripKind: TripKind;
  departureDate: string;
  returnDate: string;
  travellers: string;
}

export type FormField = "origin" | "destination" | "departureDate" | "returnDate" | "travellers";
export type FormErrors = Partial<Record<FormField, string>>;

export type ValidationResult =
  | { ok: true; request: TripRequest }
  | { ok: false; errors: FormErrors };

/** The most travellers one request may have: the owner's answer to PRD Q14 (2026-10-30). */
export const MAX_TRAVELLERS = 9;

export const EMPTY_FORM: TripFormValues = {
  origin: "",
  destination: "",
  tripKind: "ROUND_TRIP",
  departureDate: "",
  returnDate: "",
  travellers: "1",
};

/** The Indore to Goa scenario from the PRD, with sample dates. */
export const EXAMPLE_FORM: TripFormValues = {
  origin: "Indore",
  destination: "Goa",
  tripKind: "ROUND_TRIP",
  departureDate: "2026-12-01",
  returnDate: "2026-12-05",
  travellers: "2",
};

export function validateTripForm(values: TripFormValues): ValidationResult {
  const errors: FormErrors = {};
  const origin = values.origin.trim();
  const destination = values.destination.trim();

  if (origin === "") {
    errors.origin = "Enter where the trip starts.";
  }
  if (destination === "") {
    errors.destination = "Enter where you are going.";
  }

  if (values.departureDate === "") {
    errors.departureDate = "Choose a departure date.";
  } else if (!isValidIsoDate(values.departureDate)) {
    errors.departureDate = "Enter a real date.";
  }

  const departureOk = errors.departureDate === undefined;
  if (values.tripKind === "ROUND_TRIP") {
    if (values.returnDate === "") {
      errors.returnDate = "Choose a return date for a round trip.";
    } else if (!isValidIsoDate(values.returnDate)) {
      errors.returnDate = "Enter a real date.";
    } else if (departureOk && values.returnDate < values.departureDate) {
      errors.returnDate = "The return date must be on or after the departure date.";
    }
  }

  const travellerText = values.travellers.trim();
  const travellerCount = /^\d+$/.test(travellerText) ? Number(travellerText) : Number.NaN;
  if (Number.isNaN(travellerCount) || travellerCount < 1) {
    errors.travellers = "Enter a whole number of at least 1.";
  } else if (travellerCount > MAX_TRAVELLERS) {
    errors.travellers = `A request can have at most ${MAX_TRAVELLERS} travellers.`;
  }

  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }

  const isOneWay = values.tripKind === "ONE_WAY";
  const returnDate = isOneWay
    ? null
    : values.tripKind === "SAME_DAY_RETURN"
      ? values.departureDate
      : values.returnDate;

  return {
    ok: true,
    request: {
      trip_type: isOneWay ? "ONE_WAY" : "ROUND_TRIP",
      origin: { name: origin },
      destination: { name: destination },
      departure_date: values.departureDate,
      return_date: returnDate,
      travellers: Array.from({ length: travellerCount }, () => ({ age: null })),
      preferences: null,
    },
  };
}
