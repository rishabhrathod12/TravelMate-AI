import { useEffect, useState } from "react";

import { fetchHealth } from "../api/health";

type State =
  | { kind: "loading" }
  | { kind: "online"; service: string; version: string }
  | { kind: "offline" };

/**
 * The one real call the app makes: `GET /health`. If the backend is not
 * running, the rest of the prototype still works with its demo data.
 */
export function BackendStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal).then(
      (health) => setState({ kind: "online", service: health.service, version: health.version }),
      () => {
        if (!controller.signal.aborted) {
          setState({ kind: "offline" });
        }
      },
    );
    return () => controller.abort();
  }, [attempt]);

  function retry() {
    setState({ kind: "loading" });
    setAttempt((value) => value + 1);
  }

  return (
    <div className={`backend-status backend-${state.kind}`} role="status" aria-live="polite">
      {state.kind === "loading" && <span>Backend: checking…</span>}
      {state.kind === "online" && (
        <span>
          Backend: online · {state.service} v{state.version}
        </span>
      )}
      {state.kind === "offline" && (
        <>
          <span>Backend: not reachable. The demo screens still work.</span>
          <button type="button" className="button button-small button-quiet" onClick={retry}>
            Retry
          </button>
        </>
      )}
    </div>
  );
}
