import type { Summary } from "../types";
import { money } from "../format";

export function SummaryStrip({ summary }: { summary: Summary }) {
  const stats = [
    { label: "Inventory value", value: money(summary.inventory_value), tone: "" },
    { label: "Critical items", value: String(summary.critical_count), tone: summary.critical_count > 0 ? "critical" : "" },
    { label: "Low items", value: String(summary.low_count), tone: summary.low_count > 0 ? "warning" : "" },
    { label: "Expiry alerts", value: String(summary.expiry_alerts), tone: summary.expiry_alerts > 0 ? "warning" : "" },
    { label: "Open orders", value: String(summary.open_orders), tone: "" },
    {
      label: "Budget left this month",
      value: money(summary.budget_remaining),
      tone: summary.budget_remaining < 0 ? "critical" : "",
    },
  ];
  return (
    <dl className="strip" aria-label="Inventory summary">
      {stats.map((s) => (
        <div key={s.label} className={`stat ${s.tone}`}>
          <dt>{s.label}</dt>
          <dd>{s.value}</dd>
        </div>
      ))}
    </dl>
  );
}
