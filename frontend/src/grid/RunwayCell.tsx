import type { ItemRow } from "../types";
import { daysText } from "../format";
import { Runway } from "../components/Runway";

/** The runway bar for one inventory row, with the days of stock written under it. */
export function RunwayCell({ row }: { row: ItemRow }) {
  return (
    <div className="grid-runway">
      <Runway days={row.days_left} lead={row.fastest_lead_time_days} risk={row.risk} />
      <span>{row.days_left === null ? "No usage on record" : `${daysText(row.days_left)} left`}</span>
    </div>
  );
}
