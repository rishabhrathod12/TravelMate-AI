import { createMockVoiceAdapter } from "./mockAdapter";
import type { VoiceAdapter } from "./VoiceAdapter";

/**
 * Chooses the voice back end. No real adapter exists yet (ADR 0002), so a production build gets
 * `null` and the interface says voice is unavailable. A development build gets the labelled mock,
 * so the interface can be built and reviewed. Mock and real voice are never mixed.
 */
export function chooseVoiceAdapter(allowMock: boolean = true): VoiceAdapter | null {
  // `import.meta.env.DEV` is a build-time constant, so a production build drops the mock entirely.
  if (import.meta.env.DEV && allowMock) {
    return createMockVoiceAdapter();
  }
  return null;
}
