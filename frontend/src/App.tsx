import { useEffect, useState } from "react";

const API = "http://127.0.0.1:8000";

type Item = {
  item: string;
  unit: string;
  stock: number;
  daily_usage: number;
  incoming: number;
  days_left: number | null;
  risk: "ok" | "warning" | "critical";
};

type Option = {
  name: string;
  unit_price: number;
  qty: number;
  total: number;
  lead_time_days: number;
  reliability: number;
  needs_approval: boolean;
  chosen: boolean;
};

type Recommendation = {
  days_left: number | null;
  message: string;
  options: Option[];
  choice: { supplier: string; reason: string; source: string } | null;
  explanation: { text: string; source: string };
};

type TimelineEvent = { type: string; detail: string; time: string };

type Order = {
  id: number;
  supplier_name: string;
  qty: number;
  total: number;
  status: string;
  item: string;
  timeline: TimelineEvent[];
};

function formatDays(days: number | null): string {
  if (days === null) return "No usage";
  return String(Math.round(days * 10) / 10);
}

function money(value: number): string {
  return `$${value.toFixed(2)}`;
}

function choiceLabel(source: string): string {
  if (source === "gemini") return "Chosen by Gemini";
  if (source === "rules") return "Only one supplier qualifies";
  return "Chosen by rules (AI unavailable)";
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.join(" ");
    return "Request failed.";
  } catch {
    return "Request failed.";
  }
}

export default function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Item | null>(null);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [orderMsg, setOrderMsg] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [openOrder, setOpenOrder] = useState<number | null>(null);

  function loadItems() {
    fetch(`${API}/items`)
      .then((response) => {
        if (!response.ok) throw new Error(`Server returned ${response.status}`);
        return response.json();
      })
      .then(setItems)
      .catch(() =>
        setError("Cannot reach the backend. Is it running on port 8000?")
      );
  }

  function loadOrders() {
    fetch(`${API}/orders`)
      .then((response) => response.json())
      .then(setOrders)
      .catch(() => setOrderMsg("Could not load orders."));
  }

  useEffect(() => {
    loadItems();
    loadOrders();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const payment = params.get("payment");
    if (payment === "authorized") {
      setBanner(
        `Payment authorized for order ${params.get("order")}. The money is reserved, not charged.`
      );
    } else if (payment === "cancelled") {
      setBanner("Payment was cancelled. No money was reserved.");
    }
    if (payment) window.history.replaceState({}, "", window.location.pathname);
  }, []);

  function getRecommendation(row: Item) {
    setSelected(row);
    setRec(null);
    setRecError(null);
    setOrderMsg(null);
    setLoading(true);
    fetch(`${API}/recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        stock: row.stock,
        incoming: row.incoming,
        daily_usage: row.daily_usage,
        buffer_days: 3,
        item: row.item,
      }),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Server returned ${response.status}`);
        return response.json();
      })
      .then(setRec)
      .catch(() => setRecError("Could not get a recommendation."))
      .finally(() => setLoading(false));
  }

  async function createOrder(supplierName: string) {
    if (!selected) return;
    setOrderMsg(null);
    try {
      const response = await fetch(`${API}/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stock: selected.stock,
          incoming: selected.incoming,
          daily_usage: selected.daily_usage,
          buffer_days: 3,
          item: selected.item,
          supplier: supplierName,
        }),
      });
      if (!response.ok) {
        setOrderMsg(await readError(response));
        return;
      }
      setOrderMsg(`Order created with ${supplierName}. It now waits for approval.`);
      loadOrders();
    } catch {
      setOrderMsg("Could not reach the backend.");
    }
  }

  async function orderAction(id: number, action: "approve" | "reject") {
    setOrderMsg(null);
    try {
      const response = await fetch(`${API}/orders/${id}/${action}`, {
        method: "POST",
      });
      if (!response.ok) setOrderMsg(await readError(response));
    } catch {
      setOrderMsg("Could not reach the backend.");
    }
    loadOrders();
  }

  async function payOrder(id: number) {
    setOrderMsg(null);
    try {
      const response = await fetch(`${API}/orders/${id}/pay`, { method: "POST" });
      if (!response.ok) {
        setOrderMsg(await readError(response));
        return;
      }
      const body = await response.json();
      if (!body.approval_url) {
        setOrderMsg("PayPal did not return an approval link.");
        loadOrders();
        return;
      }
      window.location.href = body.approval_url;
    } catch {
      setOrderMsg("Could not reach the backend.");
    }
  }

  async function confirmDelivery(id: number) {
    setOrderMsg(null);
    try {
      const response = await fetch(`${API}/orders/${id}/confirm-delivery`, {
        method: "POST",
      });
      if (!response.ok) {
        setOrderMsg(await readError(response));
      } else {
        setOrderMsg(
          `Delivery confirmed for order ${id}. Payment captured and stock updated.`
        );
        loadItems();
      }
    } catch {
      setOrderMsg("Could not reach the backend.");
    }
    loadOrders();
  }

  async function resetDemo() {
    if (!window.confirm("Reset the demo? This clears all orders and restores stock.")) {
      return;
    }
    try {
      const response = await fetch(`${API}/demo/reset`, { method: "POST" });
      if (!response.ok) {
        setError(await readError(response));
        return;
      }
      setSelected(null);
      setRec(null);
      setOpenOrder(null);
      setBanner(null);
      setOrderMsg(null);
      setError(null);
      loadItems();
      loadOrders();
    } catch {
      setError("Could not reach the backend.");
    }
  }

  const timelineOrder = orders.find((o) => o.id === openOrder) ?? null;

  return (
    <main>
      <h1>RescueBuy</h1>
      <p className="sub">Inventory</p>
      {banner && <p className="banner">{banner}</p>}
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>Stock</th>
            <th>Used per day</th>
            <th>Days left</th>
            <th>Risk</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.item}>
              <td>{row.item}</td>
              <td>
                {row.stock} {row.unit}
              </td>
              <td>{row.daily_usage}</td>
              <td>{formatDays(row.days_left)}</td>
              <td>
                <span className={`badge ${row.risk}`}>{row.risk}</span>
              </td>
              <td>
                <button disabled={loading} onClick={() => getRecommendation(row)}>
                  Get recommendation
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected && (
        <section className="panel">
          <h2>Recommendation for {selected.item}</h2>
          {loading && <p>Asking Gemini to compare suppliers...</p>}
          {recError && <p className="error">{recError}</p>}
          {rec && (
            <>
              <p>{rec.message}</p>
              <p>{rec.explanation.text}</p>
              <p className="note">
                {rec.explanation.source === "gemini"
                  ? "Summary written by Gemini."
                  : "Plain summary (AI unavailable)."}
              </p>

              {rec.options.length > 0 && (
                <>
                  <div className="scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Supplier</th>
                          <th>Unit price</th>
                          <th>Quantity</th>
                          <th>Total</th>
                          <th>Delivery</th>
                          <th>Reliability</th>
                          <th>Owner approval</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {rec.options.map((o) => (
                          <tr key={o.name} className={o.chosen ? "chosen" : ""}>
                            <td>
                              {o.name}
                              {o.chosen && <span className="badge pick">chosen</span>}
                            </td>
                            <td>{money(o.unit_price)}</td>
                            <td>{o.qty}</td>
                            <td>{money(o.total)}</td>
                            <td>{o.lead_time_days} days</td>
                            <td>{Math.round(o.reliability * 100)}%</td>
                            <td>{o.needs_approval ? "Required" : "Not needed"}</td>
                            <td>
                              <button onClick={() => createOrder(o.name)}>
                                Create order
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {rec.choice && (
                    <>
                      <p>
                        <strong>{rec.choice.supplier}:</strong> {rec.choice.reason}
                      </p>
                      <p className="note">{choiceLabel(rec.choice.source)}</p>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </section>
      )}

      <section className="panel">
        <h2>Orders</h2>
        {orderMsg && <p className="note">{orderMsg}</p>}
        {orders.length === 0 ? (
          <p className="note">No orders yet.</p>
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
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.id}>
                      <td>{o.id}</td>
                      <td>{o.item}</td>
                      <td>{o.supplier_name}</td>
                      <td>{o.qty}</td>
                      <td>{money(o.total)}</td>
                      <td>
                        <span className="badge status">{o.status}</span>
                      </td>
                      <td>
                        {o.status === "PENDING_APPROVAL" && (
                          <>
                            <button onClick={() => orderAction(o.id, "approve")}>
                              Approve
                            </button>
                            <button onClick={() => orderAction(o.id, "reject")}>
                              Reject
                            </button>
                          </>
                        )}
                        {o.status === "APPROVED" && (
                          <button onClick={() => payOrder(o.id)}>
                            Pay with PayPal
                          </button>
                        )}
                        {o.status === "PAYMENT_STARTED" && (
                          <span className="note">Waiting for buyer approval</span>
                        )}
                        {o.status === "AUTHORIZED" && (
                          <button onClick={() => confirmDelivery(o.id)}>
                            Confirm delivery
                          </button>
                        )}
                        {o.status === "DELIVERED_CAPTURED" && (
                          <span className="note">Delivered and paid</span>
                        )}
                        <button
                          onClick={() => setOpenOrder(openOrder === o.id ? null : o.id)}
                        >
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
                      <strong>{e.type}</strong> {e.detail}
                      <span className="note">
                        {" "}
                        {new Date(e.time).toLocaleTimeString()}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </>
        )}
      </section>
      <p className="footer">
        <button onClick={resetDemo}>Reset demo</button>
      </p>
    </main>
  );
}