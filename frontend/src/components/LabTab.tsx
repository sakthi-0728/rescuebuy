import { useEffect, useState } from "react";

import { messageOf, post } from "../api";
import { money, plural } from "../format";
import type { LabDeferred, LabLine, LabOrdersResult, LabResult, Scenario } from "../types";

type Props = {
  onOrdersCreated: () => void;
};

type Inputs = { budget: number | null; delay: number; wait: number };

const DELAYS = [0, 1, 2, 3];
const WAITS = [0, 1, 2, 3, 4];

function request(inputs: Inputs): Promise<LabResult> {
  return post<LabResult>("/lab/simulate", {
    budget: inputs.budget,
    supplier_delay_days: inputs.delay,
    wait_days: inputs.wait,
  });
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
    return d.order_within_days === null
      ? "can wait"
      : `can wait, order within ${plural(d.order_within_days, "day")}`;
  }
  return `at risk: ${plural(d.stockout_days, "day")} without stock even from the fastest supplier`;
}

type CardProps = {
  scenario: Scenario;
  recommended: boolean;
  creating: boolean;
  onCreate: (key: string) => void;
};

function ScenarioCard({ scenario: s, recommended, creating, onCreate }: CardProps) {
  const saving = s.savings_vs_baseline;
  return (
    <article className={`scenario${recommended ? " recommended" : ""}`}>
      <header>
        <h3>{s.name}</h3>
        {recommended && <span className="badge pick">Recommended</span>}
      </header>
      <p className="hint">{s.description}</p>

      <dl className="kv">
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
        <ul className="plain">
          {s.exposed.map((e) => (
            <li key={e.item} className="bad">
              {e.item}: about {plural(e.stockout_days, "day")} without stock
            </li>
          ))}
        </ul>
      )}

      <h4>Buy now</h4>
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

      {s.deferred.length > 0 && (
        <>
          <h4>Waits</h4>
          <ul className="plain">
            {s.deferred.map((d) => (
              <li key={d.item} className={d.can_wait ? "" : "bad"}>
                <strong>{d.item}</strong>
                <span className="sub">{deferredText(d)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="hint">
        {saving === 0
          ? "Spends the same as the baseline."
          : saving > 0
            ? `Spends ${money(saving)} less than the baseline.`
            : `Spends ${money(-saving)} more than the baseline.`}
      </p>
      <button className="primary" disabled={s.bought.length === 0 || creating} onClick={() => onCreate(s.key)}>
        Create proposed orders
      </button>
    </article>
  );
}

export function LabTab({ onOrdersCreated }: Props) {
  const [result, setResult] = useState<LabResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [budgetText, setBudgetText] = useState("");
  const [delay, setDelay] = useState(0);
  const [wait, setWait] = useState(2);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<LabOrdersResult | null>(null);

  // First load uses the remaining monthly budget.
  useEffect(() => {
    let cancelled = false;
    request({ budget: null, delay: 0, wait: 2 })
      .then((r) => {
        if (cancelled) return;
        setResult(r);
        setBudgetText(String(r.inputs.budget));
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
  }, []);

  function parsedBudget(): number | null | "invalid" {
    if (budgetText.trim() === "") return null;
    const value = Number(budgetText);
    return Number.isFinite(value) && value >= 0 ? value : "invalid";
  }

  async function run() {
    const budget = parsedBudget();
    if (budget === "invalid") {
      setError("Enter a budget of 0 or more.");
      return;
    }
    setLoading(true);
    setError(null);
    setCreated(null);
    try {
      const r = await request({ budget, delay, wait });
      setResult(r);
      setBudgetText(String(r.inputs.budget));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setLoading(false);
    }
  }

  async function createOrders(key: string) {
    const budget = parsedBudget();
    if (budget === "invalid" || !result) return;
    setCreating(true);
    setError(null);
    try {
      const made = await post<LabOrdersResult>("/lab/orders", {
        scenario: key,
        budget: result.inputs.budget,
        supplier_delay_days: result.inputs.supplier_delay_days,
        wait_days: result.inputs.wait_days,
      });
      setCreated(made);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="lab-title">
        <div className="panel-head">
          <h2 id="lab-title">Decision Lab</h2>
          <p className="hint">Compare purchasing strategies before spending anything.</p>
        </div>
        <form
          className="lab-form"
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
        >
          <label>
            Budget ($)
            <input
              type="number"
              min="0"
              step="10"
              value={budgetText}
              onChange={(e) => setBudgetText(e.target.value)}
            />
          </label>
          <label>
            If suppliers deliver
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
          <button className="primary" type="submit" disabled={loading}>
            Compare strategies
          </button>
          <button type="button" disabled={loading} onClick={() => setBudgetText("")}>
            Use my remaining budget
          </button>
        </form>
        <p className="hint">
          Nothing here orders or charges anything. Creating proposed orders only adds them to your Orders list,
          where they wait for your approval.
        </p>
        {error && (
          <p className="error-box" role="alert">
            {error}
          </p>
        )}
      </section>

      {loading && !result && <p className="empty">Running scenarios…</p>}

      {result && (
        <>
          <section className="panel" aria-busy={loading}>
            <p className="lead">{result.explanation.text}</p>
            <p className="hint">
              {result.explanation.source === "gemini" ? "Summary written by Gemini." : "Plain summary (AI unavailable)."}{" "}
              {/estimate/i.test(result.explanation.text) ? "" : `${result.estimate_note} `}
              {result.baseline}
            </p>
            {result.unfillable.length > 0 && (
              <p className="error-box" role="status">
                No eligible supplier for {result.unfillable.join(", ")}. Escalate to the owner.
              </p>
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

          {result.scenarios.every((s) => s.bought.length === 0 && s.deferred.length === 0) ? (
            <p className="empty">Nothing needs replenishing right now, so there is nothing to compare.</p>
          ) : (
            <div className="scenarios">
              {result.scenarios.map((s) => (
                <ScenarioCard
                  key={s.key}
                  scenario={s}
                  recommended={s.key === result.recommended}
                  creating={creating}
                  onCreate={(key) => void createOrders(key)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
