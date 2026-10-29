import { describe, expect, test } from "vitest";

import { chooseVoiceAdapter } from "./config";

describe("chooseVoiceAdapter", () => {
  test("the dev adapters can be switched off, and then there is no adapter", () => {
    expect(chooseVoiceAdapter(false)).toBeNull();
    expect(chooseVoiceAdapter(false, "session")).toBeNull();
  });

  // Vitest runs with DEV true, as `npm run dev` does. A production build is covered by the
  // bundle check recorded in the plan (the mock's strings are absent from dist).
  test("a development build gets the labelled mock by default", () => {
    const adapter = chooseVoiceAdapter(true, undefined);

    expect(adapter?.isMock).toBe(true);
    expect(adapter?.hearsUser).toBe(true);
  });

  test("VITE_VOICE_ADAPTER=session gives the session-only adapter, which hears nothing", () => {
    const adapter = chooseVoiceAdapter(true, "session");

    expect(adapter?.isMock).toBe(false);
    expect(adapter?.hearsUser).toBe(false);
    expect(adapter?.playsAudio).toBe(false);
  });

  test("any other value falls back to the mock, never to something real", () => {
    expect(chooseVoiceAdapter(true, "realtime")?.isMock).toBe(true);
    expect(chooseVoiceAdapter(true, "")?.isMock).toBe(true);
  });
});
