import { ROUTES, type Route } from "../lib/route";

/** Compass-style mark, drawn inline so no image file is needed. */
function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M16 6l4 10-4 10-4-10z" fill="currentColor" />
    </svg>
  );
}

export function AppHeader({ route }: { route: Route }) {
  return (
    <header className="app-header">
      <a className="brand" href="#/plan">
        <BrandMark />
        <span>TravelMate AI</span>
      </a>
      <nav aria-label="Main">
        <ul className="nav-list">
          {ROUTES.map((item) => (
            <li key={item.route}>
              <a
                className="nav-link"
                href={item.href}
                aria-current={item.route === route ? "page" : undefined}
              >
                {item.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
