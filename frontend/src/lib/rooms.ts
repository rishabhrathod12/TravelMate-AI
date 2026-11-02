/**
 * Reading the answer to "How many rooms do you need?".
 *
 * The number of rooms has no default (PRD Q14), so this accepts only an answer that plainly is a
 * number of rooms, from 1 to 9 (the same ceiling as travellers). Anything else, including a
 * sentence that merely contains a number ("4 people"), is not read as an answer.
 */

export const MIN_ROOMS = 1;
export const MAX_ROOMS = 9;

const WORDS: Record<string, number> = {
  one: 1,
  a: 1,
  single: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
};

/** "2", "two", "2 rooms", "two rooms please", "I need 3 rooms", "a single room". */
const ANSWER =
  /^\s*(?:(?:i|we)\s+(?:need|want|would\s+like|'d\s+like)\s+)?(\d{1,2}|[a-z]+)\s*(?:rooms?)?\s*(?:please|pls)?\s*[.!]?\s*$/i;

/** The number of rooms the text answers with, or null if it is not a clear answer from 1 to 9. */
export function parseRooms(text: string): number | null {
  const match = ANSWER.exec(text);
  if (match === null) {
    return null;
  }
  const token = (match[1] ?? "").toLowerCase();
  const rooms = /^\d+$/.test(token) ? Number(token) : (WORDS[token] ?? null);
  if (rooms === null || !Number.isInteger(rooms) || rooms < MIN_ROOMS || rooms > MAX_ROOMS) {
    return null;
  }
  // "a" alone is not an answer; it only means one in "a room" / "a single room".
  if (token === "a" && !/rooms?/i.test(text)) {
    return null;
  }
  return rooms;
}
