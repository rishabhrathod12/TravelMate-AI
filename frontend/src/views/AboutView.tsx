export function AboutView() {
  return (
    <section className="about" aria-labelledby="about-title">
      <h1 id="about-title">About TravelMate AI</h1>
      <p>
        TravelMate AI is a portfolio project for learning Agentic AI engineering. It is meant to
        research trip options, compare them, estimate costs and draft an itinerary, always with a
        human approving any real booking.
      </p>

      <div className="card">
        <h2>What exists today</h2>
        <ul>
          <li>
            A backend with one real endpoint, <code>/health</code>, which this app calls to show the
            status at the top of the page.
          </li>
          <li>
            Tested backend rules for trips, money, source labels, quotes and the booking lifecycle.
            No screen reads them from the backend yet.
          </li>
          <li>This interface, which runs entirely in your browser.</li>
        </ul>
      </div>

      <div className="card">
        <h2>What is demo data</h2>
        <p>
          Every option, price, availability label, cost line and itinerary shown after “Preview with
          demo data” is a hand-written sample marked MOCK. None of it is real, and none of it comes
          from an AI model.
        </p>
      </div>

      <div className="card">
        <h2>Not built yet</h2>
        <ul>
          <li>Real transport, hotel and weather providers.</li>
          <li>AI agents, language models and the planning workflow.</li>
          <li>A database, saved trips and accounts.</li>
          <li>The approval flow. Real booking and payment are disabled.</li>
        </ul>
      </div>

      <div className="card safety-callout">
        <h2>Safety</h2>
        <p>
          Human approval is mandatory before any real booking or payment, and booking is switched
          off. Nothing in this app can book or pay.
        </p>
      </div>
    </section>
  );
}
