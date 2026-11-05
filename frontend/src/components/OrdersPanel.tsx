import type { Order } from "../types";
import { money } from "../format";

type Props = {
  orders: Order[];
  message: string | null;
  openOrder: number | null;
  onToggleTimeline: (id: number) => void;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onPay: (id: number) => void;
  onRestart: (id: number) => void;
  onConfirm: (order: Order) => void;
};

const STATUS_LABEL: Record<string, string> = {
  PENDING_APPROVAL: "Awaiting your approval",
  APPROVED: "Approved, ready to pay",
  REJECTED: "Rejected",
  PAYMENT_STARTED: "Waiting for PayPal",
  AUTHORIZED: "Funds reserved",
  DELIVERED_CAPTURED: "Delivered and paid",
};

export function OrdersPanel(props: Props) {
  const { orders, message, openOrder, onToggleTimeline } = props;
  const timelineOrder = orders.find((o) => o.id === openOrder) ?? null;

  return (
    <section className="panel" aria-labelledby="orders-title">
      <div className="panel-head">
        <h2 id="orders-title">Orders</h2>
      </div>
      {message && (
        <p className="banner" role="status">
          {message}
        </p>
      )}
      {orders.length === 0 ? (
        <p className="empty">No orders yet. Review a reorder above and create one.</p>
      ) : (
        <>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Item</th>
                  <th>Supplier</th>
                  <th>Quantity</th>
                  <th>Total</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.id}</td>
                    <td>{o.item}</td>
                    <td>{o.supplier_name}</td>
                    <td className="num">{o.qty}</td>
                    <td className="num">{money(o.total)}</td>
                    <td>
                      <span className="badge status">{STATUS_LABEL[o.status] ?? o.status}</span>
                    </td>
                    <td className="actions">
                      {o.status === "PENDING_APPROVAL" && (
                        <>
                          <button className="primary" onClick={() => props.onApprove(o.id)}>
                            Approve
                          </button>
                          <button onClick={() => props.onReject(o.id)}>Reject</button>
                        </>
                      )}
                      {o.status === "APPROVED" && (
                        <button className="primary" onClick={() => props.onPay(o.id)}>
                          Pay with PayPal
                        </button>
                      )}
                      {o.status === "PAYMENT_STARTED" && (
                        <button onClick={() => props.onRestart(o.id)}>Restart payment</button>
                      )}
                      {o.status === "AUTHORIZED" && (
                        <button className="primary" onClick={() => props.onConfirm(o)}>
                          Confirm delivery
                        </button>
                      )}
                      <button onClick={() => onToggleTimeline(o.id)}>
                        {openOrder === o.id ? "Hide timeline" : "Timeline"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {timelineOrder && (
            <div className="timeline">
              <h3>Order {timelineOrder.id} timeline</h3>
              <ol>
                {timelineOrder.timeline.map((e, i) => (
                  <li key={i}>
                    {e.detail}
                    <span className="sub">
                      {e.type} at {new Date(e.time).toLocaleTimeString()}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}
    </section>
  );
}
