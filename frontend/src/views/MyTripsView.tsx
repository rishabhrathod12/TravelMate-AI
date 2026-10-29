import { StatusMessage } from "../components/StatusMessage";

export function MyTripsView() {
  return (
    <section aria-labelledby="trips-title">
      <h1 id="trips-title">My trips</h1>
      <StatusMessage kind="empty" title="No saved trips">
        Saving trips needs the database, which arrives in Milestone 9. This prototype stores nothing:
        a refresh clears everything you entered.
      </StatusMessage>
    </section>
  );
}
