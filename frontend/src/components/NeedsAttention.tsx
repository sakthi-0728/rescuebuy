import type { Alert, ItemRow } from "../types";
import { Runway } from "./Runway";

type Props = {
  alerts: Alert[];
  items: ItemRow[];
  busy: boolean;
  onReview: (item: string) => void;
};

export function NeedsAttention({ alerts, items, busy, onReview }: Props) {
  return (
    <section className="panel" aria-labelledby="attention-title">
      <div className="panel-head">
        <h2 id="attention-title">Needs attention</h2>
        <p className="hint">Bar: days of stock left, across 14 days. Tick: fastest delivery.</p>
      </div>
      {alerts.length === 0 ? (
        <p className="empty">Nothing needs attention. Every item has enough stock and nothing expires soon.</p>
      ) : (
        <ul className="alerts">
          {alerts.map((a) => {
            const row = items.find((i) => i.item === a.item);
            return (
              <li key={`${a.item}-${a.kind}`} className={`alert ${a.severity}`}>
                <span className={`sev ${a.severity}`}>{a.severity === "critical" ? "Critical" : "Warning"}</span>
                <div className="alert-body">
                  <strong>{a.title}</strong>
                  <p>{a.reason}</p>
                </div>
                {row && a.kind === "stockout" && (
                  <Runway days={row.days_left} lead={row.fastest_lead_time_days} risk={row.risk} />
                )}
                {a.action === "review_reorder" && a.open_order && (
                  <span className="in-progress">Order {a.open_order.id} in progress</span>
                )}
                {a.action === "review_reorder" && !a.open_order && (
                  <button className="primary" disabled={busy} onClick={() => onReview(a.item)}>
                    Review reorder
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
