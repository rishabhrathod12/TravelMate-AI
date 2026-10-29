import type { Money } from "../contracts/types";
import { formatMoney } from "../lib/money";

export function MoneyText({ money }: { money: Money }) {
  return <span className="money">{formatMoney(money)}</span>;
}
