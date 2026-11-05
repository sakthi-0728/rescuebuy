const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function money(value: number): string {
  return usd.format(value);
}

export function plural(n: number, word: string): string {
  return n === 1 ? `${n} ${word}` : `${n} ${word}s`;
}

export function daysText(days: number | null): string {
  if (days === null) return "No usage";
  return plural(Math.round(days * 10) / 10, "day");
}

export function expiryText(daysToExpiry: number | null): string {
  if (daysToExpiry === null) return "No expiry";
  if (daysToExpiry < 0) return `Expired ${plural(-daysToExpiry, "day")} ago`;
  if (daysToExpiry === 0) return "Expires today";
  return `In ${plural(daysToExpiry, "day")}`;
}

export function riskLabel(risk: "ok" | "warning" | "critical"): string {
  if (risk === "critical") return "Critical";
  if (risk === "warning") return "Low";
  return "Healthy";
}

export function deliveriesText(n: number): string {
  return n === 1 ? "1 past delivery" : `${n} past deliveries`;
}

export function moneyShort(value: number): string {
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

export function monthLabel(month: string): string {
  return new Date(`${month}-01T00:00:00`).toLocaleString("en-US", { month: "short" });
}

export function monthTitle(month: string): string {
  return new Date(`${month}-01T00:00:00`).toLocaleString("en-US", { month: "long", year: "numeric" });
}
