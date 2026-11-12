import type { DecisionRecord } from "../types";
import { daysText, money } from "../format";

const PICKED_BY: Record<DecisionRecord["chosen_by"], string> = {
  gemini: "Picked by Gemini from the suppliers that passed the rules.",
  fallback: "Picked by the rules, lowest total cost (AI unavailable).",
  rules: "Only one supplier passed the rules.",
  owner: "Picked by you on the review screen.",
  decision_lab: "Picked by the Decision Lab strategy you chose.",
};

function reliabilityText(reliability: number | null, deliveries: number): string {
  if (reliability === null) return deliveries === 0 ? "Unknown (no history)" : `Unknown (${deliveries} on record)`;
  return `${Math.round(reliability * 100)}% on time`;
}

/** The record saved with the order when it was proposed. It is read back, never recalculated. */
export function WhyThisOrder({ record, item, unit }: { record: DecisionRecord; item: string; unit: string }) {
  return (
    <section className="why" aria-label={`Why this order for ${item}`}>
      <h4>Why this order</h4>
      <p className="why-reason">{record.reason}</p>
      <p className="hint">{PICKED_BY[record.chosen_by]}</p>

      <h5 className="why-subhead">Suppliers that passed the rules</h5>
      <ul className="why-options">
        {record.considered.map((c) => (
          <li key={c.name} className={`why-option${c.chosen ? " chosen" : ""}`}>
            <div className="why-option-name">
              <strong>{c.name}</strong>
              {c.chosen && <span className="badge pick">Chosen</span>}
              <span className="sub">
                {c.qty} {unit} at {money(c.unit_price)}
                {c.delivery_fee > 0 ? `, ${money(c.delivery_fee)} delivery` : ", free delivery"}
              </span>
            </div>
            <div>
              <span className="mini-label">Total</span>
              {money(c.total)}
            </div>
            <div>
              <span className="mini-label">Arrives</span>
              {daysText(c.lead_time_days)}
            </div>
            <div>
              <span className="mini-label">Reliability</span>
              {reliabilityText(c.reliability, c.deliveries_on_record)}
            </div>
          </li>
        ))}
      </ul>

      {record.rejected.length > 0 && (
        <div className="why-block">
          <h5>Not eligible</h5>
          <ul>
            {record.rejected.map((r) => (
              <li key={r.name}>
                <strong>{r.name}:</strong> {r.reasons.join(" ")}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="why-cols">
        <div className="why-block">
          <h5>Rules applied</h5>
          <ul>
            {record.rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
        <div className="why-block">
          <h5>Assumptions</h5>
          <ul>
            {record.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      </div>

      {record.budget_remaining_before !== null && (
        <p className="hint">
          Budget left this month when the order was proposed: {money(record.budget_remaining_before)}. These are
          estimates calculated by the app, not guarantees.
        </p>
      )}
    </section>
  );
}
