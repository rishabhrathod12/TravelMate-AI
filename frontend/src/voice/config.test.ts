import { describe, expect, test } from "vitest";

import { chooseVoiceAdapter } from "./config";

describe("chooseVoiceAdapter", () => {
  test("the mock can be switched off, and then there is no adapter", () => {
    expect(chooseVoiceAdapter(false)).toBeNull();
  });

  // Vitest runs with DEV true, as `npm run dev` does. A production build is covered by the
  // bundle check recorded in the plan (the mock's strings are absent from dist).
  test("a development build gets the labelled mock", () => {
    const adapter = chooseVoiceAdapter();

    expect(adapter?.isMock).toBe(true);
  });
});
