import { useEffect, useState } from "react";

import { get, messageOf } from "../api";
import { money, moneyShort, monthLabel, monthTitle, plural } from "../format";
import type { AnalyticsData } from "../types";
import { LedgerGrid } from "./LedgerGrid";
import { SkeletonPanel } from "./Skeleton";

function Body({ months }: { months: number }) {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    get<AnalyticsData>(`/analytics?months=${months}`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(messageOf(e));
      });
    return () => {
      cancelled = true;
    };
  }, [months]);

  if (error) {
    return (
      <p className="error-box" role="alert">
        {error}
      </p>
    );
  }
  if (!data) {
    return (
      <>
        <SkeletonPanel lines={4} label="Loading analytics" />
        <SkeletonPanel lines={5} label="Loading chart" />
      </>
    );
  }

  const b = data.budget;
  const maxMonth = Math.max(1, ...data.monthly_spend.map((m) => m.total));
  const categoryTotal = data.by_category.reduce((sum, c) => sum + c.total, 0);
  const maxCategory = Math.max(1, ...data.by_category.map((c) => c.total));
  const meterTone = b.over_budget ? "critical" : b.used_pct >= 80 ? "warning" : "ok";
  const criticalItems = data.stock_risk.critical;
  const biggestExcess = data.excess.items[0];

  return (
    <>
      <div className="tiles insights" role="group" aria-label="Key figures">
        <div className="tile">
          <span className="tile-label">Potential savings</span>
          <span className="tile-value">{money(data.savings.total)}</span>
          <span className="tile-sub">Best supplier vs costliest eligible, on current reorders. An estimate.</span>
        </div>
        <div className={`tile ${data.excess.value > 0 ? "warning" : ""}`}>
          <span className="tile-label">Cash in excess stock</span>
          <span className="tile-value">{money(data.excess.value)}</span>
          <span className="tile-sub">
            {data.excess.items.length === 0
              ? `Nothing above ${data.excess.threshold_days} days of use.`
              : `${plural(data.excess.items.length, "item")} above ${data.excess.threshold_days} days of use.`}
          </span>
        </div>
        <div className={`tile ${criticalItems.length > 0 ? "critical" : ""}`}>
          <span className="tile-label">Stockout risk</span>
          <span className="tile-value">{criticalItems.length}</span>
          <span className="tile-sub">
            {criticalItems.length === 0
              ? "No item is critical right now."
              : `Critical: ${criticalItems.join(", ")}.${
                  data.stock_risk.low.length > 0 ? ` ${data.stock_risk.low.length} more running low.` : ""
                }`}
          </span>
        </div>
        <div className={`tile ${b.remaining < 0 ? "critical" : ""}`}>
          <span className="tile-label">Budget left</span>
          <span className="tile-value">{money(b.remaining)}</span>
          <span className="tile-sub">{monthTitle(b.month)}. {b.used_pct}% of {money(b.monthly)} used.</span>
        </div>
      </div>

      {biggestExcess && (
        <p className="insight-note">
          <strong>What stands out.</strong> {money(biggestExcess.excess_value)} is tied up in extra{" "}
          {biggestExcess.item}: {biggestExcess.excess_qty} of the {biggestExcess.stock} {biggestExcess.unit} on hand is
          more than {data.excess.threshold_days} days of use. Ordering less of it next time keeps that cash for items that
          run out sooner. <span className="hint">Calculated from your records, not written by AI.</span>
        </p>
      )}

      <section className="panel" aria-labelledby="budget-title">
        <div className="panel-head">
          <h2 id="budget-title">Budget for {monthTitle(b.month)}</h2>
          <p className="hint">Monthly replenishment budget: {money(b.monthly)}</p>
        </div>
        <div className="meter" role="img" aria-label={`${b.used_pct} percent of the monthly budget used`}>
          <div className={`meter-fill ${meterTone}`} style={{ width: `${Math.min(100, b.used_pct)}%` }} />
        </div>
        <p className="lead">
          Spent {money(b.spent)} ({b.used_pct}%).{" "}
          {b.over_budget ? (
            <strong className="bad">Over budget by {money(-b.remaining)}.</strong>
          ) : (
            <strong>{money(b.remaining)} left.</strong>
          )}
        </p>
        <p className="reason">
          Replenishing everything that needs it would cost <strong>{money(data.upcoming.cost)}</strong>.{" "}
          {data.upcoming.vs_remaining < 0 ? (
            <span className="bad">That is {money(-data.upcoming.vs_remaining)} more than you have left.</span>
          ) : (
            <span>That leaves {money(data.upcoming.vs_remaining)} of the budget.</span>
          )}
        </p>
        <p className="hint">{data.upcoming.basis}</p>
        {data.upcoming.items.length > 0 && (
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Supplier</th>
                  <th>Quantity</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {data.upcoming.items.map((i) => (
                  <tr key={i.item}>
                    <td>{i.item}</td>
                    <td>{i.supplier}</td>
                    <td className="num">{i.qty}</td>
                    <td className="num">{money(i.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="trend-title">
        <div className="panel-head">
          <h2 id="trend-title">Spending by month</h2>
          <p className="hint">
            <span className="swatch demo" /> Demo history <span className="swatch real" /> Your real orders
          </p>
        </div>
        <ul className="bars" aria-label="Monthly spending">
          {data.monthly_spend.map((m) => {
            const real = (m.real_total / maxMonth) * 100;
            const demo = ((m.total - m.real_total) / maxMonth) * 100;
            return (
              <li key={m.month} className="bar-col">
                <span className="bar-value">{moneyShort(m.total)}</span>
                <div className="bar-track">
                  <div className="bar demo" style={{ height: `${demo}%` }} />
                  <div className="bar real" style={{ height: `${real}%` }} />
                </div>
                <span className="bar-label">{monthLabel(m.month)}</span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="panel" aria-labelledby="category-title">
        <div className="panel-head">
          <h2 id="category-title">Spending by category</h2>
          <p className="hint">Last {plural(data.months, "month")}</p>
        </div>
        <ul className="hbars">
          {data.by_category.map((c) => (
            <li key={c.category}>
              <span className="hbar-label">{c.category}</span>
              <div className="hbar-track">
                <div className="hbar" style={{ width: `${(c.total / maxCategory) * 100}%` }} />
              </div>
              <span className="hbar-value">
                {money(c.total)} ({categoryTotal > 0 ? Math.round((c.total / categoryTotal) * 100) : 0}%)
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" aria-labelledby="excess-title">
        <div className="panel-head">
          <h2 id="excess-title">Excess stock</h2>
          <p className="hint">Stock beyond {data.excess.threshold_days} days of use</p>
        </div>
        {data.excess.items.length === 0 ? (
          <p className="empty">No item holds more than {data.excess.threshold_days} days of stock.</p>
        ) : (
          <>
            <p className="lead">{money(data.excess.value)} is tied up in stock you will not use for a while.</p>
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Lasts</th>
                    <th>Excess</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {data.excess.items.map((i) => (
                    <tr key={i.item}>
                      <td>{i.item}</td>
                      <td>{plural(i.days_left, "day")}</td>
                      <td className="num">
                        {i.excess_qty} of {i.stock} {i.unit}
                        <span className="sub">above {data.excess.threshold_days} days of use</span>
                      </td>
                      <td className="num">
                        {money(i.excess_value)}
                        <span className="sub">
                          {i.excess_qty} {i.unit} at {money(i.unit_cost)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="savings-title">
        <div className="panel-head">
          <h2 id="savings-title">Savings from comparing suppliers</h2>
        </div>
        {data.savings.items.length === 0 ? (
          <p className="empty">No saving to report right now.</p>
        ) : (
          <>
            <p className="lead">
              Choosing the best supplier per unit instead of the costliest saves about{" "}
              <strong>{money(data.savings.total)}</strong> on the current reorders.
            </p>
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Best supplier</th>
                    <th>Costliest eligible</th>
                    <th>Saving</th>
                  </tr>
                </thead>
                <tbody>
                  {data.savings.items.map((i) => (
                    <tr key={i.item}>
                      <td>{i.item}</td>
                      <td>
                        {i.best_supplier}
                        <span className="sub">{money(i.best_total)}</span>
                      </td>
                      <td>
                        {i.baseline_supplier}
                        <span className="sub">{money(i.baseline_total)} for the same quantity</span>
                      </td>
                      <td className="num">{money(i.saving)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <p className="hint">{data.savings.basis} This is an estimate, not money already saved.</p>
      </section>
    </>
  );
}

export function AnalyticsTab() {
  const [months, setMonths] = useState(6);
  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <h2>Time range</h2>
          <label className="inline">
            Show
            <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
              <option value={3}>last 3 months</option>
              <option value={6}>last 6 months</option>
            </select>
          </label>
        </div>
        <p className="hint">
          History before your first real order is sample data. Real orders are added when you confirm delivery.
        </p>
      </section>
      <Body key={months} months={months} />
      <section className="panel" aria-labelledby="ledger-title">
        <div className="panel-head">
          <h2 id="ledger-title">Purchase ledger</h2>
          <p className="hint">Every purchase behind the figures above. Sort, search and export it.</p>
        </div>
        <LedgerGrid />
      </section>
    </div>
  );
}
