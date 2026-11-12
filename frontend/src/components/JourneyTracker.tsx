import type { Order } from "../types";
import { timeShort } from "../format";

const STEPS = ["Proposed", "Approved", "Funds reserved", "Delivered and paid"];
const STEP_EVENTS = ["ORDER_CREATED", "APPROVED", "AUTHORIZED", "DELIVERED_CAPTURED"];

/** How many milestones the order has reached. */
function reached(status: string): number {
  switch (status) {
    case "PENDING_APPROVAL":
      return 1;
    case "APPROVED":
    case "PAYMENT_STARTED":
      return 2;
    case "AUTHORIZED":
      return 3;
    case "DELIVERED_CAPTURED":
      return 4;
    default:
      return 1;
  }
}

function eventTime(order: Order, type: string): string | null {
  const event = order.timeline.find((e) => e.type === type);
  return event ? timeShort(event.time) : null;
}

export function JourneyTracker({ order }: { order: Order }) {
  if (order.status === "REJECTED") {
    return <p className="journey-rejected">Rejected. Nothing was reserved or charged.</p>;
  }
  const done = reached(order.status);
  return (
    <ol className="journey" aria-label="Order progress">
      {STEPS.map((label, i) => {
        const state = i < done ? "done" : i === done ? "current" : "todo";
        const waiting = state === "current" && order.status === "PAYMENT_STARTED" && i === 2;
        return (
          <li key={label} className={`step ${state}`} aria-current={state === "current" ? "step" : undefined}>
            <span className="node" aria-hidden="true">
              {state === "done" ? "✓" : i + 1}
            </span>
            <span className="step-label">{label}</span>
            <span className="step-time">
              {state === "done" ? eventTime(order, STEP_EVENTS[i]) : waiting ? "Waiting for PayPal" : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const PREVIEW: { label: string; note: string }[] = [
  { label: "Proposed", note: "Rules check the suppliers and you see why one was picked." },
  { label: "Approved", note: "Nothing moves until you approve." },
  { label: "Funds reserved", note: "PayPal holds the money. It is not charged." },
  { label: "Delivered and paid", note: "You confirm delivery. Then PayPal captures and stock rises." },
];

/** The same four steps with no order yet, so an empty Orders screen explains the flow. */
export function JourneyPreview() {
  return (
    <ol className="journey preview" aria-label="How an order moves">
      {PREVIEW.map((s, i) => (
        <li key={s.label} className="step todo">
          <span className="node" aria-hidden="true">
            {i + 1}
          </span>
          <span className="step-label">{s.label}</span>
          <span className="step-note">{s.note}</span>
        </li>
      ))}
    </ol>
  );
}
