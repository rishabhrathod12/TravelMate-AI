import { useEffect, useId, useRef, useState } from "react";

import { ROUTES, type Route } from "../lib/route";
import { MenuIcon, PlaneIcon } from "./home/icons";

export function AppHeader({ route }: { route: Route }) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const root = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);

  // Escape closes the menu and returns focus to its button; a click elsewhere closes it too.
  useEffect(() => {
    if (!open) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        toggle.current?.focus();
      }
    }
    function onPointer(event: MouseEvent) {
      if (root.current !== null && !root.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  return (
    <header className="app-header" ref={root}>
      <a className="brand" href="#/plan">
        <PlaneIcon />
        <span>TravelMate AI</span>
      </a>
      <button
        type="button"
        ref={toggle}
        className="menu-button"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label="Menu"
        onClick={() => setOpen((value) => !value)}
      >
        <MenuIcon />
      </button>
      {open && (
        <nav id={menuId} className="menu-panel" aria-label="Main">
          <ul className="nav-list">
            {ROUTES.map((item) => (
              <li key={item.route}>
                <a
                  className="nav-link"
                  href={item.href}
                  aria-current={item.route === route ? "page" : undefined}
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}
