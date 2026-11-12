import type { ItemRow } from "../types";
import { daysText, expiryText, money, riskLabel } from "../format";
import { Runway } from "./Runway";

type Props = {
  items: ItemRow[];
  busy: boolean;
  onReview: (item: string) => void;
};

const RANK = { critical: 0, warning: 1, ok: 2 };

function byUrgency(a: ItemRow, b: ItemRow): number {
  if (RANK[a.risk] !== RANK[b.risk]) return RANK[a.risk] - RANK[b.risk];
  const da = a.days_left ?? Number.POSITIVE_INFINITY;
  const db = b.days_left ?? Number.POSITIVE_INFINITY;
  if (da !== db) return da < db ? -1 : 1;
  return a.item.localeCompare(b.item);
}

export function InventoryCards({ items, busy, onReview }: Props) {
  return (
    <ul className="inv-grid">
      {[...items].sort(byUrgency).map((row) => (
        <li key={row.item} className={`inv-card ${row.risk}`}>
          <header>
            <h3>{row.item}</h3>
            <span className={`badge ${row.risk}`}>{riskLabel(row.risk)}</span>
          </header>
          <p className="sub">
            {row.category} · {row.stock} {row.unit} in stock
          </p>
          <p className="inv-days">
            {row.days_left === null ? "No usage" : daysText(row.days_left)}
            <span> left at {row.daily_usage} {row.unit} a day</span>
          </p>
          <Runway days={row.days_left} lead={row.fastest_lead_time_days} risk={row.risk} />
          <footer>
            <div className="chips-row">
              {row.days_to_expiry !== null && (
                <span className={`chip-static${row.days_to_expiry <= 3 ? " warn" : ""}`}>
                  Expiry: {expiryText(row.days_to_expiry)}
                </span>
              )}
              <span className="chip-static">Value {money(row.inventory_value)}</span>
            </div>
            {row.open_order ? (
              <span className="in-progress">Order {row.open_order.id} in progress</span>
            ) : (
              <button disabled={busy} className={row.risk === "ok" ? "" : "primary"} onClick={() => onReview(row.item)}>
                Review reorder
              </button>
            )}
          </footer>
        </li>
      ))}
    </ul>
  );
}
