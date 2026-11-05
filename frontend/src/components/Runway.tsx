import type { Risk } from "../types";
import { daysText } from "../format";

const SPAN_DAYS = 14;

type Props = {
  days: number | null;
  lead: number | null;
  risk: Risk;
};

/** Bar length is days of stock left. The tick marks the fastest delivery. */
export function Runway({ days, lead, risk }: Props) {
  const fill = days === null ? 100 : Math.min(100, (days / SPAN_DAYS) * 100);
  const tick = lead === null ? null : Math.min(100, (lead / SPAN_DAYS) * 100);
  const label =
    `${daysText(days)} of stock` +
    (lead === null ? ", no approved supplier" : `, fastest delivery ${daysText(lead)}`);

  return (
    <div className="runway" role="img" aria-label={label}>
      <div className={`runway-fill ${risk}`} style={{ width: `${fill}%` }} />
      {tick !== null && <div className="runway-tick" style={{ left: `${tick}%` }} />}
    </div>
  );
}
