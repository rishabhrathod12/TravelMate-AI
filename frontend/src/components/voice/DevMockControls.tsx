import type { DevMockControls as Controls } from "../../voice/VoiceAdapter";

/**
 * Development only. Shown solely when the adapter is a development mock that exposes these
 * controls, never for a real adapter. It lets a developer exercise states a mock cannot reach by
 * itself.
 */
export function DevMockControls({ controls }: { controls: Controls }) {
  return (
    <details className="dev-mock-controls">
      <summary>Developer controls (development build only)</summary>
      <p className="field-hint">
        These act on the scripted voice. They do not represent anything a real user can do.
      </p>
      <div className="button-row">
        <button
          type="button"
          className="button button-quiet button-small"
          onClick={controls.simulateUserPhrase}
        >
          Simulate: user says a phrase
        </button>
        <button
          type="button"
          className="button button-quiet button-small"
          onClick={controls.denyMicrophoneNextTime}
        >
          Simulate: block the microphone next time
        </button>
        <button
          type="button"
          className="button button-quiet button-small"
          onClick={controls.simulateError}
        >
          Simulate: drop the connection
        </button>
      </div>
    </details>
  );
}
