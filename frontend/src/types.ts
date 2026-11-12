export type Risk = "ok" | "warning" | "critical";

export type OpenOrder = { id: number; status: string };

export type ItemRow = {
  item: string;
  category: string;
  unit: string;
  stock: number;
  daily_usage: number;
  incoming: number;
  unit_cost: number;
  inventory_value: number;
  criticality: number;
  days_left: number | null;
  risk: Risk;
  fastest_lead_time_days: number | null;
  expiry_date: string | null;
  days_to_expiry: number | null;
  expiring_unused: number;
  last_restocked: string | null;
  open_order: OpenOrder | null;
};

export type Alert = {
  item: string;
  kind: "stockout" | "expiry";
  severity: "critical" | "warning";
  title: string;
  reason: string;
  action: "review_reorder" | null;
  days_left: number | null;
  open_order: OpenOrder | null;
};

export type Summary = {
  item_count: number;
  inventory_value: number;
  critical_count: number;
  low_count: number;
  expiry_alerts: number;
  open_orders: number;
  budget_remaining: number;
};

export type TopAction = {
  item: string;
  unit: string;
  days_left: number | null;
  supplier: string;
  qty: number;
  total: number;
  lead_time_days: number;
  fits_budget: boolean;
  budget_remaining: number;
};

export type Dashboard = {
  demo_data: boolean;
  summary: Summary;
  attention: Alert[];
  top_action: TopAction | null;
};

export type Option = {
  name: string;
  unit_price: number;
  delivery_fee: number;
  min_order_qty: number;
  qty: number;
  total: number;
  lead_time_days: number;
  margin_days: number | null;
  reliability: number | null;
  deliveries_on_record: number;
  needs_approval: boolean;
  note: string | null;
  chosen: boolean;
};

export type Rejected = { name: string; reasons: string[] };

export type Recommendation = {
  item: string;
  days_left: number | null;
  risk: Risk;
  message: string;
  options: Option[];
  rejected: Rejected[];
  choice: { supplier: string; reason: string; source: string } | null;
  explanation: { text: string; source: string };
};

export type TimelineEvent = { type: string; detail: string; time: string };

export type DecisionConsidered = {
  name: string;
  qty: number;
  unit_price: number;
  delivery_fee: number;
  total: number;
  lead_time_days: number;
  margin_days: number | null;
  reliability: number | null;
  deliveries_on_record: number;
  chosen: boolean;
};

/** Why an order was proposed. Calculated and stored when the order was created. */
export type DecisionRecord = {
  chosen: {
    supplier: string;
    qty: number;
    total: number;
    unit_price: number;
    delivery_fee: number;
    lead_time_days: number;
  };
  chosen_by: "gemini" | "fallback" | "rules" | "owner" | "decision_lab";
  reason: string;
  considered: DecisionConsidered[];
  rejected: Rejected[];
  rules: string[];
  assumptions: string[];
  budget_remaining_before: number | null;
};

/** A PayPal webhook event whose signature was verified, matched to the order by PayPal id. */
export type PaypalEvent = {
  id: string;
  type: string | null;
  summary: string | null;
  resource_id: string | null;
  time: string;
};

export type Order = {
  id: number;
  item: string;
  supplier_name: string;
  qty: number;
  total: number;
  status: string;
  timeline: TimelineEvent[];
  decision: DecisionRecord | null;
  paypal_events: PaypalEvent[];
};

export type AnalyticsData = {
  demo_data: boolean;
  months: number;
  budget: {
    month: string;
    monthly: number;
    spent: number;
    remaining: number;
    used_pct: number;
    over_budget: boolean;
  };
  monthly_spend: { month: string; total: number; real_total: number }[];
  by_category: { category: string; total: number }[];
  upcoming: {
    cost: number;
    vs_remaining: number;
    basis: string;
    items: { item: string; supplier: string; qty: number; total: number }[];
  };
  excess: {
    threshold_days: number;
    value: number;
    items: {
      item: string;
      unit: string;
      stock: number;
      unit_cost: number;
      days_left: number;
      excess_qty: number;
      excess_value: number;
    }[];
  };
  stock_risk: { critical: string[]; low: string[] };
  savings: {
    basis: string;
    total: number;
    items: {
      item: string;
      best_supplier: string;
      baseline_supplier: string;
      best_total: number;
      baseline_total: number;
      saving: number;
    }[];
  };
};

export type LabLine = {
  item: string;
  supplier: string;
  qty: number;
  total: number;
  lead_time_days: number;
  arrives_in_days: number;
  margin_days: number | null;
  stockout_days: number;
};

export type LabDeferred = {
  item: string;
  can_wait: boolean;
  margin_days: number | null;
  stockout_days: number;
  order_within_days: number | null;
};

export type Scenario = {
  key: string;
  name: string;
  description: string;
  spend: number;
  budget_remaining: number;
  over_budget: boolean;
  bought: LabLine[];
  deferred: LabDeferred[];
  /** stockout_days is null when no eligible supplier is left, so there is no way to say how long. */
  exposed: { item: string; stockout_days: number | null; reason?: "no_supplier" }[];
  savings_vs_baseline: number;
};

/** What-if inputs for the Decision Lab stress test. All read-only. */
export type Stress = {
  demand_change_pct: number;
  unavailable_suppliers: string[];
  supplier_delays: Record<string, number>;
  active: boolean;
};

export type SupplierRow = {
  name: string;
  items: string[];
  fastest_lead_days: number;
  reliability: number | null;
  deliveries_on_record: number;
  delivery_fee: number;
  only_option_for: string[];
};

export type Unfilled = {
  item: string;
  days_left: number | null;
  fastest_supplier: string | null;
  fastest_lead_days: number | null;
};

export type Purchase = {
  item: string;
  category: string;
  supplier: string;
  qty: number;
  total: number;
  purchased_on: string;
  is_demo: boolean;
};

export type LabResult = {
  inputs: { budget: number; supplier_delay_days: number; wait_days: number };
  stress: Stress;
  unfilled: Unfilled[];
  estimate_note: string;
  baseline: string;
  scenarios: Scenario[];
  recommended: string;
  unfillable: string[];
  explanation: { text: string; source: string };
};

export type LabOrdersResult = {
  scenario: string;
  created: Order[];
  skipped: { item: string; reason: string }[];
};

export type AssistantResponse = {
  question: string;
  tool: string;
  routed_by: "gemini" | "keywords" | "rules";
  answer: { text: string; source: "gemini" | "calculated" };
  basis: string[];
  data: Record<string, unknown>;
  needs_clarification: boolean;
  suggestions: string[];
  as_of: string;
};
