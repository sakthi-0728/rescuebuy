import { useEffect, useRef, useState } from "react";

import { messageOf, post } from "../api";
import { money, plural } from "../format";
import type { LabDeferred, LabLine, LabOrdersResult, LabResult, Scenario } from "../types";
import { DecisionMatrix, STRATEGY_NAMES } from "./DecisionMatrix";
import { Skeleton, SkeletonPanel } from "./Skeleton";
import { NO_STRESS, StressTest, stressIsActive, type StressInputs } from "./StressTest";

type Props = {
  onOrdersCreated: () => void;
};

type Inputs = { budget: number | null; delay: number; wait: number };

const DELAYS = [0, 1, 2, 3];
const WAITS = [0, 1, 2, 3, 4];

const SHORT = STRATEGY_NAMES;

function request(inputs: Inputs, stress: StressInputs): Promise<LabResult> {
  return post<LabResult>("/lab/simulate", {
    budget: inputs.budget,
    supplier_delay_days: inputs.delay,
    wait_days: inputs.wait,
    supplier_delays: stress.delays,
    unavailable_suppliers: stress.unavailable,
    demand_change_pct: stress.demandPct,
  });
}

function exposedText(e: { item: string; stockout_days: number | null }): string {
  return e.stockout_days === null
    ? `${e.item}: no eligible supplier is left, so it may run out`
    : `${e.item}: about ${plural(e.stockout_days, "day")} without stock`;
}

function lineText(line: LabLine): string {
  const spare =
    line.margin_days === null
      ? "no stockout expected"
      : line.margin_days >= 0
        ? `${plural(line.margin_days, "day")} of stock to spare`
        : `${plural(line.stockout_days, "day")} without stock`;
  return `arrives in ${plural(line.arrives_in_days, "day")}, ${spare}`;
}

function deferredText(d: LabDeferred): string {
  if (d.can_wait) {
    return d.order_within_days === null ? "can wait" : `can wait, order within ${plural(d.order_within_days, "day")}`;
  }
  return `at risk: ${plural(d.stockout_days, "day")} without stock even from the fastest supplier`;
}

type ChartProps = {
  scenarios: Scenario[];
  budget: number;
  selected: string;
  recommended: string;
  onSelect: (key: string) => void;
};

/** One bar per strategy against the budget line. The part over budget is drawn in red. */
function StrategyChart({ scenarios, budget, selected, recommended, onSelect }: ChartProps) {
  const top = Math.max(budget, ...scenarios.map((s) => s.spend), 1) * 1.08;
  const pct = (value: number) => (value / top) * 100;
  return (
    <>
      <ul className="strategies" aria-label="Strategies compared with your budget">
        {scenarios.map((s) => {
          const within = Math.min(s.spend, budget);
          return (
            <li key={s.key}>
              <button className="strategy" aria-pressed={selected === s.key} onClick={() => onSelect(s.key)}>
                <span className="strategy-name">
                  {SHORT[s.key] ?? s.name}
                  {s.key === recommended && <span className="badge pick">Recommended</span>}
                </span>
                <span className="strategy-track" aria-hidden="true">
                  <span className="strategy-fill within" style={{ width: `${pct(within)}%` }} />
                  {s.over_budget && (
                    <span className="strategy-fill over" style={{ left: `${pct(budget)}%`, width: `${pct(s.spend - budget)}%` }} />
                  )}
                  <span className="strategy-budget" style={{ left: `${pct(budget)}%` }} />
                </span>
                <span className="strategy-amount">
                  {money(s.spend)}
                  {s.over_budget && <span className="bad"> over by {money(s.spend - budget)}</span>}
                </span>
                <span className={`risk-chip ${s.exposed.length > 0 ? "bad" : "good"}`}>
                  {s.exposed.length === 0 ? "No stockouts" : `${plural(s.exposed.length, "item")} may run out`}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="hint">
        The thin line marks your budget ({money(budget)}). Red is the part over it. Select a strategy for the details.
      </p>
    </>
  );
}

type DetailProps = {
  scenario: Scenario;
  recommended: boolean;
  creating: boolean;
  onCreate: (key: string) => void;
};

function ScenarioDetail({ scenario: s, recommended, creating, onCreate }: DetailProps) {
  const saving = s.savings_vs_baseline;
  return (
    <section className="panel" aria-labelledby="detail-title">
      <div className="panel-head">
        <h2 id="detail-title">
          {s.name}
          {recommended && <span className="badge pick">Recommended</span>}
        </h2>
        <button className="primary" disabled={s.bought.length === 0 || creating} onClick={() => onCreate(s.key)}>
          Create proposed orders
        </button>
      </div>
      <p className="hint">{s.description}</p>

      <dl className="kv-row">
        <div>
          <dt>Spend</dt>
          <dd>{money(s.spend)}</dd>
        </div>
        <div>
          <dt>Budget left</dt>
          <dd className={s.over_budget ? "bad" : ""}>
            {s.over_budget ? `Over by ${money(-s.budget_remaining)}` : money(s.budget_remaining)}
          </dd>
        </div>
        <div>
          <dt>Stockout risk</dt>
          <dd className={s.exposed.length > 0 ? "bad" : ""}>
            {s.exposed.length === 0 ? "None expected" : `${plural(s.exposed.length, "item")} may run out`}
          </dd>
        </div>
      </dl>

      {s.exposed.length > 0 && (
        <ul className="plain exposed-list">
          {s.exposed.map((e) => (
            <li key={e.item} className="bad">
              {exposedText(e)}
            </li>
          ))}
        </ul>
      )}

      <div className="detail-cols">
        <div>
          <h3>Buy now</h3>
          {s.bought.length === 0 ? (
            <p className="hint">Nothing today.</p>
          ) : (
            <ul className="plain">
              {s.bought.map((l) => (
                <li key={l.item}>
                  <strong>{l.item}</strong> from {l.supplier}: {l.qty}, {money(l.total)}
                  <span className="sub">{lineText(l)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3>Waits</h3>
          {s.deferred.length === 0 ? (
            <p className="hint">Nothing waits.</p>
          ) : (
            <ul className="plain">
              {s.deferred.map((d) => (
                <li key={d.item} className={d.can_wait ? "" : "bad"}>
                  <strong>{d.item}</strong>
                  <span className="sub">{deferredText(d)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <p className="hint">
        {saving === 0
          ? "Spends the same as the baseline."
          : saving > 0
            ? `Spends ${money(saving)} less than the baseline.`
            : `Spends ${money(-saving)} more than the baseline.`}
      </p>
    </section>
  );
}

export function LabTab({ onOrdersCreated }: Props) {
  const [result, setResult] = useState<LabResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [budgetText, setBudgetText] = useState("");
  const [delay, setDelay] = useState(0);
  const [wait, setWait] = useState(2);
  const [stress, setStress] = useState<StressInputs>(NO_STRESS);
  const [picked, setPicked] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<LabOrdersResult | null>(null);
  const latest = useRef(0);
  const firstRun = useRef(true);

  // Every change to a setting recalculates, after a short pause so typing a budget is not one request per key.
  // A response that arrives after a newer request was sent is ignored.
  useEffect(() => {
    const trimmed = budgetText.trim();
    const budget = trimmed === "" ? null : Number(trimmed);
    if (budget !== null && !(Number.isFinite(budget) && budget >= 0)) {
      setError("Enter a budget of 0 or more.");
      setLoading(false);
      return;
    }
    setError(null);
    const wasFirst = firstRun.current;
    firstRun.current = false;
    const timer = window.setTimeout(
      () => {
        const id = ++latest.current;
        setLoading(true);
        request({ budget, delay, wait }, stress)
          .then((r) => {
            if (id !== latest.current) return;
            setResult(r);
            setCreated(null);
          })
          .catch((e: unknown) => {
            if (id === latest.current) setError(messageOf(e));
          })
          .finally(() => {
            if (id === latest.current) setLoading(false);
          });
      },
      wasFirst ? 0 : 350
    );
    return () => window.clearTimeout(timer);
  }, [budgetText, delay, wait, stress]);

  async function createOrders(key: string) {
    if (!result) return;
    setCreating(true);
    setError(null);
    try {
      const made = await post<LabOrdersResult>("/lab/orders", {
        scenario: key,
        budget: result.inputs.budget,
        supplier_delay_days: result.inputs.supplier_delay_days,
        wait_days: result.inputs.wait_days,
        supplier_delays: result.stress.supplier_delays,
        unavailable_suppliers: result.stress.unavailable_suppliers,
        demand_change_pct: result.stress.demand_change_pct,
      });
      setCreated(made);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setCreating(false);
    }
  }

  const selected = result && result.scenarios.some((s) => s.key === picked) ? picked : (result?.recommended ?? "");
  const chosen = result?.scenarios.find((s) => s.key === selected) ?? null;
  const nothingToBuy = result?.scenarios.every((s) => s.bought.length === 0 && s.deferred.length === 0);

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="lab-title">
        <div className="panel-head">
          <h2 id="lab-title">Scenario settings</h2>
          <p className="hint">Change an assumption and the strategies are compared again right away.</p>
        </div>
        <div className="lab-form">
          <label>
            Budget ($)
            <input
              type="number"
              min="0"
              step="10"
              value={budgetText}
              placeholder={result ? String(result.inputs.budget) : ""}
              onChange={(e) => setBudgetText(e.target.value)}
            />
          </label>
          <label>
            If every supplier delivers
            <select value={delay} onChange={(e) => setDelay(Number(e.target.value))}>
              {DELAYS.map((d) => (
                <option key={d} value={d}>
                  {d === 0 ? "on time" : `${plural(d, "day")} late`}
                </option>
              ))}
            </select>
          </label>
          <label>
            The rest can wait
            <select value={wait} onChange={(e) => setWait(Number(e.target.value))}>
              {WAITS.map((w) => (
                <option key={w} value={w}>
                  {w === 0 ? "no days" : plural(w, "day")}
                </option>
              ))}
            </select>
          </label>
          <button type="button" disabled={budgetText === ""} onClick={() => setBudgetText("")}>
            Use my remaining budget
          </button>
        </div>
        <p className="hint">
          Nothing here orders or charges anything. Creating proposed orders only adds them to your Orders, where they wait
          for your approval.
        </p>
        {error && (
          <p className="error-box" role="alert">
            {error}
          </p>
        )}
      </section>

      <StressTest value={stress} onChange={(next) => setStress(next)} applied={result?.stress ?? null} busy={loading} />

      {loading && !result && (
        <>
          <SkeletonPanel lines={4} label="Running scenarios" />
          <Skeleton height={120} />
        </>
      )}

      {result && (
        <>
          <section className="panel" aria-busy={loading}>
            <p className="lead">{result.explanation.text}</p>
            <p className="hint">
              {result.explanation.source === "gemini" ? "Summary written by Gemini." : "Plain summary (AI unavailable)."}{" "}
              {/estimate/i.test(result.explanation.text) ? "" : `${result.estimate_note} `}
              {result.baseline}
            </p>
            {result.unfilled.length > 0 && (
              <div className="error-box" role="status">
                <p>
                  No eligible supplier for {result.unfilled.map((u) => u.item).join(", ")}
                  {stressIsActive(stress) ? " with these what-ifs" : ""}. Every strategy counts these as at risk. Talk to the
                  owner or add a supplier.
                </p>
                {result.unfilled.map((u) =>
                  u.fastest_supplier ? (
                    <p key={u.item} className="hint">
                      {u.item}: the fastest approved supplier, {u.fastest_supplier}, delivers in{" "}
                      {plural(u.fastest_lead_days ?? 0, "day")}
                      {u.days_left === null ? "." : `, but stock lasts about ${plural(Math.round(u.days_left * 10) / 10, "day")}.`}
                    </p>
                  ) : null
                )}
              </div>
            )}
            {created && (
              <div className="banner" role="status">
                <p>
                  Created {plural(created.created.length, "proposed order")} from “{created.scenario}”. They wait for your
                  approval.
                </p>
                {created.skipped.map((k) => (
                  <p key={k.item} className="hint">
                    Skipped {k.item}: {k.reason}.
                  </p>
                ))}
                <button className="primary" onClick={onOrdersCreated}>
                  Go to orders
                </button>
              </div>
            )}
          </section>

          {nothingToBuy ? (
            <p className="empty">Nothing needs replenishing right now, so there is nothing to compare.</p>
          ) : (
            <>
              <section className="panel" aria-labelledby="chart-title">
                <div className="panel-head">
                  <h2 id="chart-title">Strategies against your budget</h2>
                </div>
                <StrategyChart
                  scenarios={result.scenarios}
                  budget={result.inputs.budget}
                  selected={selected}
                  recommended={result.recommended}
                  onSelect={setPicked}
                />
              </section>
              <section className="panel" aria-labelledby="matrix-title">
                <div className="panel-head">
                  <h2 id="matrix-title">What each strategy does</h2>
                  <p className="hint">
                    Select a strategy column to see its details below.
                    <span className="swipe-hint"> Swipe sideways to see every strategy.</span>
                  </p>
                </div>
                <DecisionMatrix
                  scenarios={result.scenarios}
                  recommended={result.recommended}
                  selected={selected}
                  budget={result.inputs.budget}
                  onSelect={setPicked}
                />
              </section>
              {chosen && (
                <ScenarioDetail
                  scenario={chosen}
                  recommended={chosen.key === result.recommended}
                  creating={creating}
                  onCreate={(key) => void createOrders(key)}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
