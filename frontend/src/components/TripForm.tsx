import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import type { TripRequest } from "../contracts/types";
import {
  EMPTY_FORM,
  EXAMPLE_FORM,
  validateTripForm,
  type FormErrors,
  type FormField,
  type TripFormValues,
  type TripKind,
} from "../lib/tripRequest";

const TRIP_KINDS: readonly { value: TripKind; label: string; hint: string }[] = [
  { value: "ONE_WAY", label: "One-way", hint: "No return date." },
  { value: "ROUND_TRIP", label: "Round trip", hint: "Return on or after the departure date." },
  { value: "SAME_DAY_RETURN", label: "Same-day return", hint: "Back on the departure date." },
];

interface FieldProps {
  id: string;
  label: string;
  error: string | undefined;
  hint?: string;
  children: (describedBy: string | undefined) => ReactNode;
}

function Field({ id, label, error, hint, children }: FieldProps) {
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy =
    [hint === undefined ? null : hintId, error === undefined ? null : errorId]
      .filter((value): value is string => value !== null)
      .join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(describedBy)}
      {hint === undefined ? null : (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      )}
      {error === undefined ? null : (
        <p className="field-error" id={errorId}>
          {error}
        </p>
      )}
    </div>
  );
}

interface TripFormProps {
  onSubmit: (request: TripRequest) => void;
}

export function TripForm({ onSubmit }: TripFormProps) {
  const [values, setValues] = useState<TripFormValues>(EMPTY_FORM);
  const [errors, setErrors] = useState<FormErrors>({});
  const formRef = useRef<HTMLFormElement>(null);
  const baseId = useId();
  const id = (field: FormField) => `${baseId}-${field}`;

  useEffect(() => {
    if (Object.keys(errors).length > 0) {
      formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    }
  }, [errors]);

  function update<K extends keyof TripFormValues>(key: K, value: TripFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = validateTripForm(values);
    if (result.ok) {
      setErrors({});
      onSubmit(result.request);
    } else {
      setErrors(result.errors);
    }
  }

  const errorCount = Object.keys(errors).length;
  const showReturnDate = values.tripKind === "ROUND_TRIP";

  return (
    <form className="card trip-form" onSubmit={handleSubmit} noValidate ref={formRef}>
      <h2 className="card-title">Trip details</h2>

      {errorCount > 0 && (
        <p className="form-summary" role="alert">
          Please fix {errorCount} {errorCount === 1 ? "field" : "fields"} below.
        </p>
      )}

      <div className="form-grid">
        <Field id={id("origin")} label="From" error={errors.origin}>
          {(describedBy) => (
            <input
              id={id("origin")}
              type="text"
              autoComplete="off"
              placeholder="e.g. Indore"
              value={values.origin}
              onChange={(event) => update("origin", event.target.value)}
              aria-invalid={errors.origin !== undefined}
              aria-describedby={describedBy}
            />
          )}
        </Field>

        <Field id={id("destination")} label="To" error={errors.destination}>
          {(describedBy) => (
            <input
              id={id("destination")}
              type="text"
              autoComplete="off"
              placeholder="e.g. Goa"
              value={values.destination}
              onChange={(event) => update("destination", event.target.value)}
              aria-invalid={errors.destination !== undefined}
              aria-describedby={describedBy}
            />
          )}
        </Field>
      </div>

      <fieldset className="trip-kind">
        <legend>Trip type</legend>
        <div className="radio-row">
          {TRIP_KINDS.map((kind) => (
            <label key={kind.value} className="radio-option">
              <input
                type="radio"
                name={`${baseId}-trip-kind`}
                value={kind.value}
                checked={values.tripKind === kind.value}
                onChange={() => update("tripKind", kind.value)}
              />
              <span>
                <span className="radio-label">{kind.label}</span>
                <span className="field-hint">{kind.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="form-grid">
        <Field id={id("departureDate")} label="Departure date" error={errors.departureDate}>
          {(describedBy) => (
            <input
              id={id("departureDate")}
              type="date"
              value={values.departureDate}
              onChange={(event) => update("departureDate", event.target.value)}
              aria-invalid={errors.departureDate !== undefined}
              aria-describedby={describedBy}
            />
          )}
        </Field>

        {showReturnDate && (
          <Field id={id("returnDate")} label="Return date" error={errors.returnDate}>
            {(describedBy) => (
              <input
                id={id("returnDate")}
                type="date"
                value={values.returnDate}
                onChange={(event) => update("returnDate", event.target.value)}
                aria-invalid={errors.returnDate !== undefined}
                aria-describedby={describedBy}
              />
            )}
          </Field>
        )}

        <Field
          id={id("travellers")}
          label="Travellers"
          error={errors.travellers}
          hint="Number of people travelling."
        >
          {(describedBy) => (
            <input
              id={id("travellers")}
              type="number"
              inputMode="numeric"
              min={1}
              step={1}
              value={values.travellers}
              onChange={(event) => update("travellers", event.target.value)}
              aria-invalid={errors.travellers !== undefined}
              aria-describedby={describedBy}
            />
          )}
        </Field>
      </div>

      <p className="field-hint">
        Budget is not part of the trip request yet, so it is not asked for here.
      </p>

      <div className="button-row">
        <button type="submit" className="button button-primary">
          Preview with demo data
        </button>
        <button
          type="button"
          className="button button-secondary"
          onClick={() => {
            setValues(EXAMPLE_FORM);
            setErrors({});
          }}
        >
          Use example trip (Indore to Goa)
        </button>
        <button
          type="button"
          className="button button-quiet"
          onClick={() => {
            setValues(EMPTY_FORM);
            setErrors({});
          }}
        >
          Clear
        </button>
      </div>
    </form>
  );
}
