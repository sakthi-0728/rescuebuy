import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/figtree";

import { get, messageOf, post } from "./api";
import { AnalyticsTab } from "./components/AnalyticsTab";
import { AssistantTab } from "./components/AssistantTab";
import { Briefing } from "./components/Briefing";
import { ConfirmDialog, type DialogSpec } from "./components/ConfirmDialog";
import { AnalyticsIcon, AskIcon, LabIcon, OrdersIcon, OverviewIcon } from "./components/Icons";
import { InventoryPanel } from "./components/InventoryPanel";
import { LabTab } from "./components/LabTab";
import { NeedsAttention } from "./components/NeedsAttention";
import { OrdersPanel } from "./components/OrdersPanel";
import { ReviewPanel } from "./components/ReviewPanel";
import { Skeleton, SkeletonPanel } from "./components/Skeleton";
import { SummaryStrip } from "./components/SummaryStrip";
import { ToastHost, type ToastItem } from "./components/Toasts";
import { money } from "./format";
import type { Dashboard, ItemRow, Order, Recommendation } from "./types";
import "./design.css";

type Tab = "overview" | "orders" | "ask" | "lab" | "analytics";

/** In the order a shop owner works: see the problem, test a plan, buy, look back. Ask sits apart. */
const TABS: { id: Tab; label: string; hint: string; Icon: ComponentType<{ className?: string }> }[] = [
  { id: "overview", label: "Overview", hint: "What needs you today", Icon: OverviewIcon },
  { id: "lab", label: "Decision Lab", hint: "Test a plan first", Icon: LabIcon },
  { id: "orders", label: "Orders", hint: "Approve, reserve, confirm", Icon: OrdersIcon },
  { id: "analytics", label: "Analytics", hint: "Where the money went", Icon: AnalyticsIcon },
  { id: "ask", label: "Ask Rescue AI", hint: "Questions about your stock", Icon: AskIcon },
];

const PAGES: Record<Tab, { title: string; subtitle: string }> = {
  overview: { title: "Overview", subtitle: "What needs your attention today." },
  orders: { title: "Orders", subtitle: "From approval to delivery, and where the money is at each step." },
  ask: { title: "Ask Rescue AI", subtitle: "Answers from your own inventory records. It never places orders." },
  lab: { title: "Decision Lab", subtitle: "Test purchasing strategies before you spend anything." },
  analytics: { title: "Analytics", subtitle: "Budget, spending and savings." },
};

/** PayPal sends the buyer back to /?payment=authorized&order=1 (or =cancelled). */
function paymentFromUrl(): { tab: Tab; toast: ToastItem | null } {
  const params = new URLSearchParams(window.location.search);
  const payment = params.get("payment");
  if (payment === "authorized") {
    return {
      tab: "orders",
      toast: {
        id: 0,
        kind: "success",
        text: `Funds reserved for order ${params.get("order")}. Nothing is charged until you confirm delivery.`,
      },
    };
  }
  if (payment === "cancelled") {
    return {
      tab: "orders",
      toast: { id: 0, kind: "info", text: "Payment was cancelled. No money was reserved. Use Restart payment to try again." },
    };
  }
  return { tab: "overview", toast: null };
}

export default function App() {
  const [initial] = useState(paymentFromUrl);
  const [tab, setTab] = useState<Tab>(initial.tab);
  const [items, setItems] = useState<ItemRow[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [openOrder, setOpenOrder] = useState<number | null>(null);
  const [failures, setFailures] = useState<Record<number, string>>({});

  const [toasts, setToasts] = useState<ToastItem[]>(initial.toast ? [initial.toast] : []);
  const nextToast = useRef(1);
  const [dialog, setDialog] = useState<{ spec: DialogSpec; resolve: (ok: boolean) => void } | null>(null);

  const notify = useCallback((kind: ToastItem["kind"], text: string, action?: ToastItem["action"]) => {
    const id = nextToast.current++;
    setToasts((t) => [...t, { id, kind, text, action }]);
  }, []);
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  function askConfirm(spec: DialogSpec): Promise<boolean> {
    return new Promise((resolve) => setDialog({ spec, resolve }));
  }
  function resolveDialog(ok: boolean) {
    dialog?.resolve(ok);
    setDialog(null);
  }

  const loadAll = useCallback(
    () => Promise.all([get<ItemRow[]>("/items"), get<Dashboard>("/dashboard"), get<Order[]>("/orders")]),
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

  // Tidy the address bar after PayPal sends the buyer back (the message was read on first render).
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("payment")) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  function reviewReorder(item: string) {
    setTab("overview");
    setSelected(item);
    setRec(null);
    setRecError(null);
    setRecLoading(true);
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setTimeout(
      () => document.getElementById("review")?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" }),
      50
    );
    post<Recommendation>("/recommend", { item })
      .then(setRec)
      .catch((e: unknown) => setRecError(messageOf(e)))
      .finally(() => setRecLoading(false));
  }

  async function createOrder(supplier: string) {
    if (!selected) return;
    try {
      const order = await post<Order>("/orders", { item: selected, supplier });
      notify("success", `Order ${order.id} created with ${supplier} for ${money(order.total)}. It waits for your approval.`, {
        label: "View orders",
        onClick: () => setTab("orders"),
      });
      await refresh();
    } catch (e) {
      notify("error", messageOf(e));
    }
  }

  async function orderStep(path: string, success: string) {
    try {
      await post<unknown>(path);
      notify("success", success);
    } catch (e) {
      notify("error", messageOf(e));
    }
    await refresh();
  }

  async function payOrder(order: Order) {
    const ok = await askConfirm({
      title: "Reserve the money with PayPal?",
      lines: [
        `You are about to reserve ${money(order.total)} for ${order.qty} ${order.item} from ${order.supplier_name} in the PayPal sandbox.`,
        "Nothing is charged now. The money is only charged when you confirm delivery.",
      ],
      confirmLabel: "Continue to PayPal",
    });
    if (!ok) return;
    try {
      const result = await post<{ approval_url: string | null }>(`/orders/${order.id}/pay`);
      if (!result.approval_url) {
        notify("error", "PayPal did not return an approval link.");
        await refresh();
        return;
      }
      window.location.href = result.approval_url;
    } catch (e) {
      notify("error", messageOf(e));
    }
  }

  async function confirmDelivery(order: Order) {
    const ok = await askConfirm({
      title: "Confirm that the delivery arrived?",
      lines: [
        `${order.qty} ${order.item} from ${order.supplier_name}.`,
        `This charges ${money(order.total)} to PayPal (sandbox) and adds the stock. It cannot be undone.`,
      ],
      confirmLabel: "Charge and add to stock",
    });
    if (!ok) return;
    try {
      await post<unknown>(`/orders/${order.id}/confirm-delivery`);
      setFailures((f) => {
        const { [order.id]: _cleared, ...rest } = f;
        return rest;
      });
      notify("success", `Delivery confirmed. ${money(order.total)} charged and ${order.qty} ${order.item} added to stock.`);
    } catch (e) {
      const detail = messageOf(e);
      const base = detail.endsWith(".") ? detail : `${detail}.`;
      const retry = detail.includes("has expired") ? "" : " You can confirm delivery again to retry.";
      setFailures((f) => ({
        ...f,
        [order.id]: `${base} Nothing was charged and your stock is unchanged.${retry}`,
      }));
      notify("error", detail);
    }
    await refresh();
  }

  async function resetDemo() {
    const ok = await askConfirm({
      title: "Reset the demo?",
      lines: ["This clears all orders and restores the sample data."],
      confirmLabel: "Reset demo",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await post<unknown>("/demo/reset");
      setSelected(null);
      setRec(null);
      setOpenOrder(null);
      await refresh();
      notify("info", "Demo reset. Sample data restored.");
    } catch (e) {
      notify("error", messageOf(e));
    }
  }

  const busy = recLoading;
  const selectedOrder = items.find((i) => i.item === selected)?.open_order ?? null;
  const openCount = dashboard?.summary.open_orders ?? 0;

  const page = PAGES[tab];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <p className="brand-name">RescueBuy</p>
            <p className="brand-tag">AI procurement for small shops</p>
          </div>
        </div>

        <nav className="side-nav" aria-label="Sections">
          {TABS.map((t) => (
            <button
              key={t.id}
              aria-current={tab === t.id ? "page" : undefined}
              className={`side-link${tab === t.id ? " active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              <t.Icon className="side-icon" />
              <span className="side-text">
                <span>{t.label}</span>
                <small>{t.hint}</small>
              </span>
              {t.id === "orders" && openCount > 0 && <span className="count">{openCount}</span>}
            </button>
          ))}
        </nav>

        <div className="side-foot">
          {dashboard?.demo_data && (
            <>
              <span className="badge demo-dark" title="Sample bakery data created on first start">
                Demo data
              </span>
              <button className="ghost-dark" onClick={() => void resetDemo()}>
                Reset demo
              </button>
            </>
          )}
        </div>
      </aside>

      <div className="content">
        <header className="page-head">
          <div>
            <h1>{page.title}</h1>
            <p>{page.subtitle}</p>
          </div>
          {dashboard && (
            <div className="head-context" aria-label="This month">
              <span className="pill">
                Budget left <strong>{money(dashboard.summary.budget_remaining)}</strong>
              </span>
              <span className="pill">
                <strong>{dashboard.summary.open_orders}</strong> open {dashboard.summary.open_orders === 1 ? "order" : "orders"}
              </span>
            </div>
          )}
        </header>

      <main>
        {error && (
          <div className="error-box" role="alert">
            <p>{error}</p>
            <button onClick={() => void refresh()}>Try again</button>
          </div>
        )}

        {tab === "overview" && (
          <>
            {loading && !dashboard && (
              <>
                <Skeleton height={120} />
                <Skeleton height={64} />
                <SkeletonPanel lines={4} label="Loading alerts" />
              </>
            )}

            {dashboard && (
              <>
                <Briefing dashboard={dashboard} busy={busy} onReview={reviewReorder} />
                <SummaryStrip summary={dashboard.summary} onOpenOrders={() => setTab("orders")} />
                <NeedsAttention alerts={dashboard.attention} items={items} busy={busy} onReview={reviewReorder} />
                <InventoryPanel items={items} busy={busy} onReview={reviewReorder} />
              </>
            )}

            {selected && (
              <ReviewPanel
                item={selected}
                rec={rec}
                loading={recLoading}
                error={recError}
                blocked={
                  selectedOrder
                    ? `Order ${selectedOrder.id} for this item is already in progress. Finish or reject it before creating another.`
                    : null
                }
                onCreateOrder={createOrder}
              />
            )}
          </>
        )}

        {tab === "orders" && (
          <>
            {loading && !dashboard && <SkeletonPanel lines={5} label="Loading orders" />}
            {dashboard && (
              <OrdersPanel
                orders={orders}
                items={items}
                failures={failures}
                openOrder={openOrder}
                onToggleTimeline={(id) => setOpenOrder(openOrder === id ? null : id)}
                onApprove={(id) => void orderStep(`/orders/${id}/approve`, `Order ${id} approved. You can now pay with PayPal.`)}
                onReject={(id) => void orderStep(`/orders/${id}/reject`, `Order ${id} rejected.`)}
                onPay={(order) => void payOrder(order)}
                onRestart={(id) => void orderStep(`/orders/${id}/restart-payment`, `Order ${id} is ready to pay again.`)}
                onConfirm={(order) => void confirmDelivery(order)}
                onGoOverview={() => setTab("overview")}
                onGoLab={() => setTab("lab")}
              />
            )}
          </>
        )}

        {/* Stays mounted so the conversation survives switching tabs. */}
        <div hidden={tab !== "ask"}>
          <AssistantTab />
        </div>

        {tab === "lab" && (
          <LabTab
            onOrdersCreated={() => {
              void refresh();
              setTab("orders");
            }}
          />
        )}

        {tab === "analytics" && <AnalyticsTab />}
      </main>
      </div>

      <ToastHost toasts={toasts} onDismiss={dismiss} />
      <ConfirmDialog spec={dialog?.spec ?? null} onResolve={resolveDialog} />
    </div>
  );
}
