import { useCallback, useState } from "react";

import type { Quote, TransportOption, TripRequest } from "../contracts/types";
import { DemoBookingRegistry, type SubmitResult } from "./demoBooking";

/** One registry per mounted page: simulated bookings live in memory and vanish on reload. */
export function useDemoBooking() {
  const [registry] = useState(() => new DemoBookingRegistry());
  const [, setVersion] = useState(0);

  const submit = useCallback(
    (option: TransportOption, quote: Quote | undefined, request: TripRequest): SubmitResult => {
      const result = registry.submit(option, quote, request);
      setVersion((version) => version + 1);
      return result;
    },
    [registry],
  );

  const find = useCallback(
    (optionId: string, request: TripRequest) => registry.find(optionId, request),
    [registry],
  );

  return { submit, find };
}
