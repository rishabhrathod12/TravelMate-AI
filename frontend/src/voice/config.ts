import { createMockVoiceAdapter } from "./mockAdapter";
import { createSessionOnlyAdapter } from "./sessionAdapter";
import type { VoiceAdapter } from "./VoiceAdapter";

/**
 * Chooses the voice back end. No real voice adapter exists yet (ADR 0002), so a production build
 * gets `null` and the interface says voice is unavailable. A development build gets the labelled
 * mock by default, so the interface can be built and reviewed, or the session-only adapter when
 * `VITE_VOICE_ADAPTER=session` is set in the shell that starts `npm run dev`. Mock, session-only
 * and real voice are never mixed.
 */
export function chooseVoiceAdapter(
  allowDevAdapters: boolean = true,
  kind: string | undefined = import.meta.env.VITE_VOICE_ADAPTER,
): VoiceAdapter | null {
  // `import.meta.env.DEV` is a build-time constant, so a production build drops both adapters.
  if (import.meta.env.DEV && allowDevAdapters) {
    return kind === "session" ? createSessionOnlyAdapter() : createMockVoiceAdapter();
  }
  return null;
}
