import type { ItemRow } from "../types";
import { daysText, expiryText, money, riskLabel } from "../format";
import { Runway } from "./Runway";

type Props = {
  items: ItemRow[];
  busy: boolean;
  onReview: (item: string) => void;
};

export function InventoryTable({ items, busy, onReview }: Props) {
  return (
    <section className="panel" aria-labelledby="inventory-title">
      <div className="panel-head">
        <h2 id="inventory-title">Inventory</h2>
      </div>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Stock</th>
              <th>Used per day</th>
              <th>Runway</th>
              <th>Status</th>
              <th>Expiry</th>
              <th>Value</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.item}>
                <td>
                  <strong>{row.item}</strong>
                  <span className="sub">{row.category}</span>
                </td>
                <td className="num">
                  {row.stock} {row.unit}
                </td>
                <td className="num">{row.daily_usage}</td>
                <td className="runway-cell">
                  <Runway days={row.days_left} lead={row.fastest_lead_time_days} risk={row.risk} />
                  <span className="sub">{daysText(row.days_left)}</span>
                </td>
                <td>
                  <span className={`badge ${row.risk}`}>{riskLabel(row.risk)}</span>
                </td>
                <td>{expiryText(row.days_to_expiry)}</td>
                <td className="num">{money(row.inventory_value)}</td>
                <td>
                  {row.open_order ? (
                    <span className="in-progress">Order {row.open_order.id} in progress</span>
                  ) : (
                    <button disabled={busy} onClick={() => onReview(row.item)}>
                      Review reorder
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
