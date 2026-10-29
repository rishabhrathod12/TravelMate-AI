import type { ReactNode } from "react";

export type StatusKind = "loading" | "error" | "empty" | "info";

interface StatusMessageProps {
  kind: StatusKind;
  title: string;
  children?: ReactNode;
}

/** One place for loading, error, empty and information messages. */
export function StatusMessage({ kind, title, children }: StatusMessageProps) {
  // Errors interrupt screen readers; the others are announced politely.
  const role = kind === "error" ? "alert" : "status";
  return (
    <div className={`status-message status-${kind}`} role={role}>
      <p className="status-title">{title}</p>
      {children === undefined ? null : <div className="status-body">{children}</div>}
    </div>
  );
}
