import type { CostEstimate } from "../contracts/types";
import { estimateTotal } from "../demo/demoData";
import { ProvenanceBadge } from "./Badges";
import { MoneyText } from "./MoneyText";

/** An itemised estimate. The total is the sum of the lines shown, never more. */
export function CostBreakdown({ estimate }: { estimate: CostEstimate }) {
  const incomplete = estimate.missing_items.length > 0;
  return (
    <div className="card">
      <table className="cost-table">
        <caption>
          Demo cost estimate{" "}
          {incomplete && <span className="badge badge-incomplete">Incomplete</span>}
        </caption>
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col">Source</th>
            <th scope="col" className="numeric">
              Amount
            </th>
          </tr>
        </thead>
        <tbody>
          {estimate.lines.length === 0 ? (
            <tr>
              <td colSpan={3}>No priced lines yet.</td>
            </tr>
          ) : (
            estimate.lines.map((line) => (
              <tr key={`${line.kind}-${line.description}`}>
                <th scope="row">{line.description}</th>
                <td>
                  <ProvenanceBadge provenance={line.provenance} />
                </td>
                <td className="numeric">
                  <MoneyText money={line.amount} />
                </td>
              </tr>
            ))
          )}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" colSpan={2}>
              Total of the lines shown
            </th>
            <td className="numeric">
              <MoneyText money={estimateTotal(estimate)} />
            </td>
          </tr>
        </tfoot>
      </table>

      {incomplete && (
        <div className="notice" role="note">
          <p className="notice-title">Not included in this total</p>
          <ul>
            {estimate.missing_items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
