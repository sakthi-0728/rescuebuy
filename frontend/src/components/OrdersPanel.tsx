import type { ItemRow, Order } from "../types";
import { money, timeShort } from "../format";
import { JourneyPreview, JourneyTracker } from "./JourneyTracker";
import { WhyThisOrder } from "./WhyThisOrder";

type Props = {
  orders: Order[];
  items: ItemRow[];
  failures: Record<number, string>;
  openOrder: number | null;
  onToggleTimeline: (id: number) => void;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onPay: (order: Order) => void;
  onRestart: (id: number) => void;
  onConfirm: (order: Order) => void;
  onGoOverview: () => void;
  onGoLab: () => void;
};

type HistoryRow = { key: string; time: string; text: string; paypal: boolean; note?: string };

/** The order's own timeline plus verified PayPal events, oldest first. */
function historyOf(order: Order): HistoryRow[] {
  const own: HistoryRow[] = order.timeline.map((e, i) => ({
    key: `t${i}`,
    time: e.time,
    text: e.detail,
    paypal: false,
  }));
  const paypal: HistoryRow[] = order.paypal_events.map((e) => ({
    key: `p${e.id}`,
    time: e.time,
    text: e.summary ?? e.type ?? "PayPal event",
    paypal: true,
    note: `${e.type ?? "Event"} · signature verified by the backend`,
  }));
  return [...own, ...paypal].sort((a, b) => Date.parse(a.time) - Date.parse(b.time));
}

function Ledger({ order, items }: { order: Order; items: ItemRow[] }) {
  const reserved = order.status === "AUTHORIZED" ? order.total : 0;
  const charged = order.status === "DELIVERED_CAPTURED" ? order.total : 0;
  const row = items.find((i) => i.item === order.item);
  const unit = row?.unit ?? "";

  let stockMain: string;
  let stockSub: string;
  if (order.status === "DELIVERED_CAPTURED") {
    stockMain = `+${order.qty} ${unit}`;
    stockSub = "added to stock";
  } else if (order.status === "REJECTED") {
    stockMain = "No change";
    stockSub = "order rejected";
  } else {
    stockMain = row ? `${row.stock} ${unit}` : "-";
    stockSub = `+${order.qty} ${unit} on delivery`;
  }

  const caption: Record<string, string> = {
    PENDING_APPROVAL: "Nothing is reserved or charged. Approve the order to continue.",
    APPROVED: "Nothing is reserved or charged yet. Paying with PayPal only reserves the money.",
    PAYMENT_STARTED: "Waiting for the buyer to approve in PayPal. Nothing is reserved yet.",
    AUTHORIZED: "The money is held, not taken. It is only charged, and stock only rises, when you confirm delivery.",
    DELIVERED_CAPTURED: "Delivery confirmed. The payment was captured and the stock was added.",
    REJECTED: "This order was rejected.",
  };

  return (
    <>
      <dl className="ledger" key={order.status}>
        <div className={`ledger-cell${reserved > 0 ? " holding" : ""}`}>
          <dt>Reserved at PayPal</dt>
          <dd>{money(reserved)}</dd>
        </div>
        <div className={`ledger-cell${charged > 0 ? " paid" : ""}`}>
          <dt>Charged</dt>
          <dd>{money(charged)}</dd>
        </div>
        <div className={`ledger-cell${order.status === "DELIVERED_CAPTURED" ? " paid" : ""}`}>
          <dt>Stock of {order.item}</dt>
          <dd>{stockMain}</dd>
          <span className="sub">{stockSub}</span>
        </div>
      </dl>
      <p className="hint ledger-caption">{caption[order.status]}</p>
    </>
  );
}

export function OrdersPanel(props: Props) {
  const { orders, items, failures, openOrder, onToggleTimeline } = props;

  if (orders.length === 0) {
    return (
      <section className="panel empty-orders" aria-labelledby="empty-orders-title">
        <h2 id="empty-orders-title">No orders yet</h2>
        <p className="lead">
          Every order follows the same four steps, and the money only moves at the last one. Start one from a
          reorder review or from a Decision Lab strategy.
        </p>
        <JourneyPreview />
        <div className="order-actions">
          <button className="primary" onClick={props.onGoOverview}>
            Review a reorder
          </button>
          <button onClick={props.onGoLab}>Open the Decision Lab</button>
        </div>
        <p className="hint">Delivery is confirmed by you. The app does not verify it, and PayPal does not guarantee it.</p>
      </section>
    );
  }

  const newestFirst = [...orders].sort((a, b) => b.id - a.id);

  return (
    <div className="stack">
      {newestFirst.map((o) => (
        <article key={o.id} className={`order-card status-${o.status.toLowerCase()}`} aria-label={`Order ${o.id}`}>
          <header className="order-head">
            <div>
              <h3>
                {o.item} <span className="order-no">order {o.id}</span>
              </h3>
              <p className="sub">
                {o.qty} from {o.supplier_name}
              </p>
            </div>
            <p className="order-total">{money(o.total)}</p>
          </header>

          <JourneyTracker order={o} />
          <Ledger order={o} items={items} />

          {o.decision && (
            <p className="why-line">
              <strong>Why:</strong> {o.decision.reason}
            </p>
          )}

          {o.status === "AUTHORIZED" && failures[o.id] && (
            <div className="error-box" role="alert">
              <p>
                <strong>Delivery could not be settled.</strong> {failures[o.id]}
              </p>
            </div>
          )}

          <div className="order-actions">
            {o.status === "PENDING_APPROVAL" && (
              <>
                <button className="primary" onClick={() => props.onApprove(o.id)}>
                  Approve order
                </button>
                <button onClick={() => props.onReject(o.id)}>Reject</button>
              </>
            )}
            {o.status === "APPROVED" && (
              <button className="primary" onClick={() => props.onPay(o)}>
                Pay with PayPal
              </button>
            )}
            {o.status === "PAYMENT_STARTED" && <button onClick={() => props.onRestart(o.id)}>Restart payment</button>}
            {o.status === "AUTHORIZED" && (
              <button className="primary" onClick={() => props.onConfirm(o)}>
                Confirm delivery
              </button>
            )}
            <button className="quiet" onClick={() => onToggleTimeline(o.id)}>
              {openOrder === o.id ? "Hide details" : "Show details"}
            </button>
          </div>

          {openOrder === o.id && (
            <div className="order-details">
              {o.decision && (
                <WhyThisOrder
                  record={o.decision}
                  item={o.item}
                  unit={items.find((i) => i.item === o.item)?.unit ?? ""}
                />
              )}
              <h4>History</h4>
              <ol className="timeline-list">
                {historyOf(o).map((h) => (
                  <li key={h.key} className={h.paypal ? "paypal-event" : undefined}>
                    {h.paypal && <span className="badge ok">PayPal</span>} {h.text}
                    <span className="sub">
                      {h.note ? `${h.note} · ` : ""}
                      {timeShort(h.time)}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
