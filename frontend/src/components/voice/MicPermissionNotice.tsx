import type { VoiceErrorCode } from "../../voice/VoiceAdapter";
import { StatusMessage } from "../StatusMessage";

const TITLE: Record<VoiceErrorCode, string> = {
  permission_denied: "Microphone access was blocked",
  no_microphone: "No microphone was found",
  connection: "The voice connection was lost",
  unknown: "Voice could not start",
};

const HELP: Record<VoiceErrorCode, string> = {
  permission_denied:
    "TravelMate can only hear you if the browser is allowed to use your microphone. Allow microphone access for this site in the browser's address bar or site settings, then try again. You can also chat by typing.",
  no_microphone:
    "Connect a microphone and try again, or chat by typing instead.",
  connection: "Check your connection and try again, or chat by typing instead.",
  unknown: "Try again, or chat by typing instead.",
};

interface MicPermissionNoticeProps {
  code: VoiceErrorCode;
  message: string;
  onRetry: () => void;
  onUseText: () => void;
  onDismiss: () => void;
}

export function MicPermissionNotice({
  code,
  message,
  onRetry,
  onUseText,
  onDismiss,
}: MicPermissionNoticeProps) {
  return (
    <StatusMessage kind="error" title={TITLE[code]}>
      <p>{HELP[code]}</p>
      <p className="field-hint">{message}</p>
      <div className="button-row">
        <button type="button" className="button button-primary button-small" onClick={onRetry}>
          Try again
        </button>
        <button type="button" className="button button-secondary button-small" onClick={onUseText}>
          Chat by text instead
        </button>
        <button type="button" className="button button-quiet button-small" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </StatusMessage>
  );
}
