import type { Dashboard, TopAction } from "../types";
import { daysText, greeting, money } from "../format";

const SPAN_DAYS = 14;

/** The briefing's picture: how long the stock lasts against how soon the delivery arrives. */
function HeroRunway({ action }: { action: TopAction }) {
  if (action.days_left === null) return null;
  const pct = (days: number) => Math.min(100, Math.max(0, (days / SPAN_DAYS) * 100));
  const spare = Math.round((action.days_left - action.lead_time_days) * 10) / 10;
  const spareText =
    spare > 0 ? `${daysText(spare)} to spare` : spare === 0 ? "No days to spare" : `${daysText(-spare)} without stock`;
  const tickAt = pct(action.lead_time_days);
  return (
    <figure
      className="hero-runway"
      aria-label={`${action.item}: ${daysText(action.days_left)} of stock left. ${action.supplier} delivers in ${daysText(action.lead_time_days)}.`}
    >
      <figcaption>
        <strong>{action.item}</strong>
        <span>next {SPAN_DAYS} days</span>
      </figcaption>
      <div className="hero-track" aria-hidden="true">
        <div className={`hero-fill${spare <= 1 ? " tight" : ""}`} style={{ width: `${pct(action.days_left)}%` }} />
        <div className="hero-tick" style={{ left: `${tickAt}%` }}>
          <span className={tickAt > 60 ? "flip" : ""}>{action.supplier} arrives</span>
        </div>
      </div>
      <div className="hero-scale" aria-hidden="true">
        <span>Today</span>
        <span>{SPAN_DAYS / 2} days</span>
        <span>{SPAN_DAYS} days</span>
      </div>
      <p className="hero-sum">
        Stock lasts <strong>{daysText(action.days_left)}</strong>. Delivery takes <strong>{daysText(action.lead_time_days)}</strong>.{" "}
        {spareText}.
      </p>
    </figure>
  );
}

type Props = {
  dashboard: Dashboard;
  busy: boolean;
  onReview: (item: string) => void;
};

/** What to do next, in plain words. Built only from calculated numbers returned by the backend. */
export function Briefing({ dashboard, busy, onReview }: Props) {
  const { summary, attention, top_action: action } = dashboard;
  const urgent = summary.critical_count + summary.low_count;
  const alert = attention.find((a) => a.kind === "stockout");

  let headline: string;
  if (urgent > 0) {
    headline = `${urgent} ${urgent === 1 ? "item needs" : "items need"} your attention today`;
  } else if (summary.expiry_alerts > 0) {
    headline = "Stock levels are fine, but something is close to expiring";
  } else {
    headline = "You are stocked up";
  }

  const parts: string[] = [];
  if (action) {
    const left = action.days_left === null ? "" : ` has about ${daysText(action.days_left)} of stock left.`;
    parts.push(`${action.item}${left || " is running low."}`);
    const budget = money(action.budget_remaining);
    parts.push(
      `${action.supplier} can deliver in ${daysText(action.lead_time_days)} for ${money(action.total)} ` +
        `(${action.qty} ${action.unit}), ` +
        (action.fits_budget
          ? `which fits the ${budget} left in this month's budget.`
          : `which is more than the ${budget} left in this month's budget.`)
    );
  } else {
    if (alert) {
      parts.push(
        alert.open_order
          ? `${alert.item} is running low and order ${alert.open_order.id} is in progress.`
          : `${alert.item} has about ${daysText(alert.days_left)} of stock left.`
      );
    }
    parts.push(
      summary.budget_remaining >= 0
        ? `${money(summary.budget_remaining)} left in this month's budget.`
        : `You are ${money(-summary.budget_remaining)} over this month's budget.`
    );
  }

  return (
    <section className="briefing" aria-labelledby="briefing-title">
      <div className="briefing-main">
        <p className="briefing-greeting">{greeting()}</p>
        <h2 id="briefing-title">{headline}</h2>
        <p className="briefing-text">{parts.join(" ")}</p>
        {action && (
          <p className="briefing-note">
            Lowest total cost among suppliers that arrive in time. Nothing is ordered until you approve.
          </p>
        )}
        {action && (
          <button className="on-dark" disabled={busy} onClick={() => onReview(action.item)}>
            Review {action.item}
          </button>
        )}
      </div>
      {action && <HeroRunway action={action} />}
    </section>
  );
}
