import { describe, expect, test } from "vitest";

import { parseRooms } from "./rooms";

describe("parseRooms", () => {
  test.each([
    ["1", 1],
    ["2", 2],
    ["9", 9],
    ["  3  ", 3],
    ["2 rooms", 2],
    ["1 room", 1],
    ["two", 2],
    ["Two rooms", 2],
    ["two rooms please", 2],
    ["I need 3 rooms", 3],
    ["we want four rooms", 4],
    ["a room", 1],
    ["a single room", null], // "single room" is not a number word on its own with "a" before it
    ["one room.", 1],
    ["NINE", 9],
  ])("%j is %s", (text, expected) => {
    // "a single room" is deliberately not accepted: only a plain number of rooms is an answer.
    expect(parseRooms(text)).toBe(expected);
  });

  test.each(["0", "10", "99", "-1", "2.5", "", "   ", "rooms", "many", "a", "four people", "4 people", "2 rooms for 4 people", "yes", "I am not sure"])(
    "%j is not an answer",
    (text) => {
      expect(parseRooms(text)).toBeNull();
    },
  );

  test("never guesses a number out of a longer sentence", () => {
    expect(parseRooms("for 2 nights please")).toBeNull();
    expect(parseRooms("the 2nd option")).toBeNull();
  });
});
