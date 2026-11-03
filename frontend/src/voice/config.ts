import { createMockVoiceAdapter } from "./mockAdapter";
import { createRealtimeAdapter } from "./realtimeAdapter";
import { createSessionOnlyAdapter } from "./sessionAdapter";
import type { VoiceAdapter } from "./VoiceAdapter";

/**
 * Chooses the voice back end. A production build gets `null` and the interface says voice is
 * unavailable. A development build gets the labelled mock by default, so the interface can be
 * built and reviewed; the session-only adapter when `VITE_VOICE_ADAPTER=session` is set in the
 * shell that starts `npm run dev`; or live spoken conversation through OpenAI Realtime when
 * `VITE_VOICE_ADAPTER=realtime` is set (ADR 0008; the server must have live voice switched on).
 * Mock, session-only and live voice are never mixed.
 */
export function chooseVoiceAdapter(
  allowDevAdapters: boolean = true,
  kind: string | undefined = import.meta.env.VITE_VOICE_ADAPTER,
): VoiceAdapter | null {
  // `import.meta.env.DEV` is a build-time constant, so a production build drops both adapters.
  if (import.meta.env.DEV && allowDevAdapters) {
    if (kind === "realtime") {
      return createRealtimeAdapter();
    }
    return kind === "session" ? createSessionOnlyAdapter() : createMockVoiceAdapter();
  }
  return null;
}
