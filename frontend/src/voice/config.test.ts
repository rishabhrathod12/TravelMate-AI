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

  test("VITE_VOICE_ADAPTER=realtime is the one opt-in to live voice, and it says so", () => {
    const adapter = chooseVoiceAdapter(true, "realtime");

    expect(adapter?.isMock).toBe(false);
    expect(adapter?.hearsUser).toBe(true);
    expect(adapter?.playsAudio).toBe(true);
    expect(adapter?.audioDisclosure).toMatch(/sent to OpenAI/);
  });

  test("any other value falls back to the mock, never to something real", () => {
    for (const value of ["", "live", "openai", "Realtime", "realtime ", "true"]) {
      expect(chooseVoiceAdapter(true, value)?.isMock).toBe(true);
    }
  });

  test("with the dev adapters off, even the live opt-in gives no adapter", () => {
    expect(chooseVoiceAdapter(false, "realtime")).toBeNull();
  });
});
