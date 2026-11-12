import type { Summary } from "../types";
import { money, moneyShort } from "../format";

type Props = {
  summary: Summary;
  onOpenOrders: () => void;
};

export function SummaryStrip({ summary, onOpenOrders }: Props) {
  const tiles = [
    { label: "Critical", value: String(summary.critical_count), tone: summary.critical_count > 0 ? "critical" : "" },
    { label: "Running low", value: String(summary.low_count), tone: summary.low_count > 0 ? "warning" : "" },
    { label: "Expiry alerts", value: String(summary.expiry_alerts), tone: summary.expiry_alerts > 0 ? "warning" : "" },
    { label: "Inventory value", value: moneyShort(summary.inventory_value), tone: "" },
    { label: "Budget left", value: money(summary.budget_remaining), tone: summary.budget_remaining < 0 ? "critical" : "" },
  ];
  return (
    <div className="tiles" role="group" aria-label="Inventory summary">
      {tiles.map((t) => (
        <div key={t.label} className={`tile ${t.tone}`}>
          <span className="tile-label">{t.label}</span>
          <span className="tile-value">{t.value}</span>
        </div>
      ))}
      <button className="tile tile-button" onClick={onOpenOrders}>
        <span className="tile-label">Open orders</span>
        <span className="tile-value">{summary.open_orders}</span>
      </button>
    </div>
  );
}
