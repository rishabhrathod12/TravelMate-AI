import type { ItineraryRequest, SamplePlanDay } from "../contracts/types";

/**
 * A fixed placeholder plan for an itinerary request (ADR 0004, phase C2). It is not written by a
 * language model, because none is connected. It names no place, activity, price, time or opening
 * hour: only the shape of a stay. Every line is labelled `SCRIPTED_SAMPLE`.
 */
export function buildSamplePlan(request: ItineraryRequest): SamplePlanDay[] {
  const where = request.destination.name;
  const last = request.days;
  const days: SamplePlanDay[] = [];
  for (let number = 1; number <= last; number += 1) {
    const titles: string[] = [];
    if (number === 1) {
      titles.push(`Arrive in ${where} and settle in`, "Easy first evening nearby");
    } else if (number === last) {
      titles.push("A relaxed last morning", `Head home from ${where}`);
    } else {
      titles.push("Morning: a main sight", "Afternoon: free time", "Evening: a local meal");
    }
    if (number === 1 && last === 1) {
      titles.splice(0, titles.length, `A day in ${where}`, "Head home");
    }
    days.push({
      day_number: number,
      items: titles.map((title) => ({ title, label: "SCRIPTED_SAMPLE" as const })),
    });
  }
  return days;
}
