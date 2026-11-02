import type { ReactNode } from "react";

/** Small inline icons, so no image files or icon packages are needed. All are decorative. */

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function MicIcon() {
  return (
    <Icon>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
    </Icon>
  );
}

export function ArrowUpIcon() {
  return (
    <Icon>
      <path d="M12 19V5" />
      <path d="M5 12l7-7 7 7" />
    </Icon>
  );
}

export function MenuIcon() {
  return (
    <Icon>
      <path d="M4 8h16" />
      <path d="M4 16h16" />
    </Icon>
  );
}

export function PlaneIcon() {
  return (
    <Icon>
      <path d="M2 16l20-8-8 20-3-9z" />
    </Icon>
  );
}
