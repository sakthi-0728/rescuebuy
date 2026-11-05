import type { Option, Recommendation } from "../types";
import { daysText, deliveriesText, money } from "../format";

type Props = {
  item: string;
  rec: Recommendation | null;
  loading: boolean;
  error: string | null;
  message: string | null;
  blocked: string | null;
  onCreateOrder: (supplier: string) => void;
};

function choiceLabel(source: string): string {
  if (source === "gemini") return "Chosen by Gemini";
  if (source === "rules") return "Only one supplier qualifies";
  return "Chosen by the rules (AI unavailable)";
}

function Reliability({ option }: { option: Option }) {
  if (option.reliability === null) {
    return (
      <>
        Unknown
        <span className="sub">
          {option.deliveries_on_record === 0
            ? "No delivery history"
            : `Only ${deliveriesText(option.deliveries_on_record)}`}
        </span>
      </>
    );
  }
  return (
    <>
      {Math.round(option.reliability * 100)}% on time
      <span className="sub">{deliveriesText(option.deliveries_on_record)} (demo history)</span>
    </>
  );
}

export function ReviewPanel({ item, rec, loading, error, message, blocked, onCreateOrder }: Props) {
  return (
    <section className="panel" id="review" aria-labelledby="review-title" aria-busy={loading}>
      <div className="panel-head">
        <h2 id="review-title">Reorder review: {item}</h2>
      </div>
      {loading && <p className="empty">Comparing suppliers…</p>}
      {error && (
        <p className="error-box" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="banner" role="status">
          {message}
        </p>
      )}
      {rec && (
        <>
          <p className="lead">{rec.explanation.text}</p>
          <p className="hint">
            {rec.explanation.source === "gemini" ? "Summary written by Gemini." : "Plain summary (AI unavailable)."}
          </p>

          {rec.options.length === 0 ? (
            <p className="empty">{rec.message}</p>
          ) : (
            <>
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Supplier</th>
                      <th>Quantity</th>
                      <th>Total</th>
                      <th>Arrives</th>
                      <th>Reliability</th>
                      <th>Order size</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rec.options.map((o) => (
                      <tr key={o.name} className={o.chosen ? "chosen" : ""}>
                        <td>
                          <strong>{o.name}</strong>
                          {o.chosen && <span className="badge pick">Recommended</span>}
                          <span className="sub">
                            {money(o.unit_price)} each, minimum {o.min_order_qty}
                          </span>
                        </td>
                        <td className="num">
                          {o.qty}
                          {o.note && <span className="sub">{o.note}</span>}
                        </td>
                        <td className="num">
                          {money(o.total)}
                          <span className="sub">
                            {o.delivery_fee > 0 ? `includes ${money(o.delivery_fee)} delivery` : "free delivery"}
                          </span>
                        </td>
                        <td>
                          {daysText(o.lead_time_days)}
                          <span className="sub">
                            {o.margin_days === null
                              ? "No stockout expected"
                              : `${daysText(o.margin_days)} before stockout`}
                          </span>
                        </td>
                        <td>
                          <Reliability option={o} />
                        </td>
                        <td>
                          {o.needs_approval ? "Large order" : "Within limit"}
                          <span className="sub">{o.needs_approval ? "Over the auto-approve limit" : "Under the limit"}</span>
                        </td>
                        <td>
                          <button
                            className={o.chosen ? "primary" : ""}
                            disabled={blocked !== null}
                            onClick={() => onCreateOrder(o.name)}
                          >
                            Create order
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {rec.choice && (
                <p className="reason">
                  <strong>{rec.choice.supplier}:</strong> {rec.choice.reason}{" "}
                  <span className="hint">{choiceLabel(rec.choice.source)}.</span>
                </p>
              )}
              <p className="hint">
                {blocked ?? "Creating an order does not charge anything. Every order waits for your approval first."}
              </p>
            </>
          )}

          {rec.rejected.length > 0 && (
            <div className="rejected">
              <h3>Not eligible</h3>
              <ul>
                {rec.rejected.map((r) => (
                  <li key={r.name}>
                    <strong>{r.name}:</strong> {r.reasons.join(" ")}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
