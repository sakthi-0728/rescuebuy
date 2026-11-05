import { useCallback, useEffect, useState } from "react";

import { get, messageOf, post } from "./api";
import { AnalyticsTab } from "./components/AnalyticsTab";
import { AssistantTab } from "./components/AssistantTab";
import { InventoryTable } from "./components/InventoryTable";
import { LabTab } from "./components/LabTab";
import { NeedsAttention } from "./components/NeedsAttention";
import { OrdersPanel } from "./components/OrdersPanel";
import { ReviewPanel } from "./components/ReviewPanel";
import { SummaryStrip } from "./components/SummaryStrip";
import { money } from "./format";
import type { Dashboard, ItemRow, Order, Recommendation } from "./types";

/** PayPal sends the buyer back to /?payment=authorized&order=1 (or =cancelled). */
function paymentBannerFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search);
  const payment = params.get("payment");
  if (payment === "authorized") {
    return `Payment authorized for order ${params.get("order")}. The money is reserved, not charged.`;
  }
  if (payment === "cancelled") {
    return "Payment was cancelled. No money was reserved. Use Restart payment to try again.";
  }
  return null;
}

type Tab = "overview" | "ask" | "lab" | "analytics";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "ask", label: "Ask Rescue AI" },
  { id: "lab", label: "Decision Lab" },
  { id: "analytics", label: "Analytics" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [items, setItems] = useState<ItemRow[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(paymentBannerFromUrl);

  const [selected, setSelected] = useState<string | null>(null);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [reviewMsg, setReviewMsg] = useState<string | null>(null);

  const [orderMsg, setOrderMsg] = useState<string | null>(null);
  const [openOrder, setOpenOrder] = useState<number | null>(null);

  const loadAll = useCallback(
    () =>
      Promise.all([get<ItemRow[]>("/items"), get<Dashboard>("/dashboard"), get<Order[]>("/orders")]),
    []
  );

  const refresh = useCallback(async () => {
    try {
      const [i, d, o] = await loadAll();
      setItems(i);
      setDashboard(d);
      setOrders(o);
      setError(null);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setLoading(false);
    }
  }, [loadAll]);

  useEffect(() => {
    let cancelled = false;
    loadAll()
      .then(([i, d, o]) => {
        if (cancelled) return;
        setItems(i);
        setDashboard(d);
        setOrders(o);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(messageOf(e));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadAll]);

  // Tidy the address bar after PayPal sends the buyer back (the banner was read on first render).
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("payment")) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  function reviewReorder(item: string) {
    setSelected(item);
    setRec(null);
    setRecError(null);
    setReviewMsg(null);
    setRecLoading(true);
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setTimeout(
      () => document.getElementById("review")?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" }),
      0
    );
    post<Recommendation>("/recommend", { item })
      .then(setRec)
      .catch((e: unknown) => setRecError(messageOf(e)))
      .finally(() => setRecLoading(false));
  }

  async function createOrder(supplier: string) {
    if (!selected) return;
    setReviewMsg(null);
    try {
      const order = await post<Order>("/orders", { item: selected, supplier });
      setReviewMsg(`Order ${order.id} created with ${supplier} for ${money(order.total)}. It now waits for your approval below.`);
      await refresh();
    } catch (e) {
      setReviewMsg(messageOf(e));
    }
  }

  async function orderStep(path: string) {
    setOrderMsg(null);
    try {
      await post<unknown>(path);
    } catch (e) {
      setOrderMsg(messageOf(e));
    }
    await refresh();
  }

  async function payOrder(id: number) {
    setOrderMsg(null);
    try {
      const result = await post<{ approval_url: string | null }>(`/orders/${id}/pay`);
      if (!result.approval_url) {
        setOrderMsg("PayPal did not return an approval link.");
        await refresh();
        return;
      }
      window.location.href = result.approval_url;
    } catch (e) {
      setOrderMsg(messageOf(e));
    }
  }

  async function confirmDelivery(order: Order) {
    const ok = window.confirm(
      `Confirm that ${order.qty} ${order.item} from ${order.supplier_name} arrived?\n\n` +
        `This charges ${money(order.total)} to PayPal (sandbox) and adds the stock.`
    );
    if (!ok) return;
    setOrderMsg(null);
    try {
      await post<unknown>(`/orders/${order.id}/confirm-delivery`);
      setOrderMsg(`Delivery confirmed for order ${order.id}. Payment captured and stock updated.`);
    } catch (e) {
      setOrderMsg(messageOf(e));
    }
    await refresh();
  }

  async function resetDemo() {
    if (!window.confirm("Reset the demo? This clears all orders and restores the sample stock.")) return;
    try {
      await post<unknown>("/demo/reset");
      setSelected(null);
      setRec(null);
      setOpenOrder(null);
      setBanner(null);
      setOrderMsg(null);
      setReviewMsg(null);
      await refresh();
    } catch (e) {
      setError(messageOf(e));
    }
  }

  const busy = recLoading;
  const selectedOrder = items.find((i) => i.item === selected)?.open_order ?? null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <h1>RescueBuy</h1>
            <p>Never run out of stock, and never pay for goods that did not arrive.</p>
          </div>
        </div>
        <div className="topbar-actions">
          {dashboard?.demo_data && (
            <span className="badge demo" title="Sample bakery data created on first start">
              Demo data
            </span>
          )}
          <button onClick={resetDemo}>Reset demo</button>
        </div>
      </header>

      <nav className="tabs" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab${tab === t.id ? " active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main>
        {banner && (
          <p className="banner" role="status">
            {banner}
          </p>
        )}
        {error && (
          <p className="error-box" role="alert">
            {error}
          </p>
        )}

        {/* Stays mounted so the conversation survives switching tabs. */}
        <div hidden={tab !== "ask"}>
          <AssistantTab />
        </div>

        {tab === "lab" && (
          <LabTab
            onOrdersCreated={() => {
              void refresh();
              setTab("overview");
            }}
          />
        )}

        {tab === "analytics" && <AnalyticsTab />}

        {tab === "overview" && (
          <>
            {loading && !error && <p className="empty">Loading inventory…</p>}

            {dashboard && (
              <>
                <SummaryStrip summary={dashboard.summary} />
                <NeedsAttention alerts={dashboard.attention} items={items} busy={busy} onReview={reviewReorder} />
                <InventoryTable items={items} busy={busy} onReview={reviewReorder} />
              </>
            )}

            {selected && (
              <ReviewPanel
                item={selected}
                rec={rec}
                loading={recLoading}
                error={recError}
                message={reviewMsg}
                blocked={
                  selectedOrder
                    ? `Order ${selectedOrder.id} for this item is already in progress. Finish or reject it before creating another.`
                    : null
                }
                onCreateOrder={createOrder}
              />
            )}

            {dashboard && (
              <OrdersPanel
                orders={orders}
                message={orderMsg}
                openOrder={openOrder}
                onToggleTimeline={(id) => setOpenOrder(openOrder === id ? null : id)}
                onApprove={(id) => void orderStep(`/orders/${id}/approve`)}
                onReject={(id) => void orderStep(`/orders/${id}/reject`)}
                onPay={(id) => void payOrder(id)}
                onRestart={(id) => void orderStep(`/orders/${id}/restart-payment`)}
                onConfirm={(order) => void confirmDelivery(order)}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}
