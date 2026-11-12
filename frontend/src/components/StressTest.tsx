import { useEffect, useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { CellValueChangedEvent, ColDef, ICellRendererParams } from "ag-grid-community";

import { get, messageOf } from "../api";
import { gridDefaults } from "../grid/setup";
import { useNarrow } from "../grid/useNarrow";
import { plural } from "../format";
import type { Stress, SupplierRow } from "../types";

export type StressInputs = {
  demandPct: number;
  delays: Record<string, number>;
  unavailable: string[];
};

export const NO_STRESS: StressInputs = { demandPct: 0, delays: {}, unavailable: [] };

export function stressIsActive(s: StressInputs): boolean {
  return s.demandPct !== 0 || s.unavailable.length > 0 || Object.values(s.delays).some((d) => d > 0);
}

const DEMAND = [
  { value: -20, label: "20% lower" },
  { value: 0, label: "as expected" },
  { value: 20, label: "20% higher" },
  { value: 50, label: "50% higher" },
  { value: 100, label: "double" },
];

type Row = SupplierRow & { delay: number; available: boolean };

type Props = {
  value: StressInputs;
  onChange: (next: StressInputs) => void;
  /** What the last run applied, so the note under the grid matches the numbers on screen. */
  applied: Stress | null;
  busy: boolean;
};

function reliabilityText(row: SupplierRow): string {
  if (row.reliability === null) return row.deliveries_on_record === 0 ? "Unknown" : `Unknown (${row.deliveries_on_record} on record)`;
  return `${Math.round(row.reliability * 100)}% on time`;
}

/**
 * The supplier grid is the control panel for the stress test. Edit a delay or untick Available and
 * the strategies are recalculated. Nothing is saved and nothing is ordered.
 */
export function StressTest({ value, onChange, applied, busy }: Props) {
  const [suppliers, setSuppliers] = useState<SupplierRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const narrow = useNarrow();

  useEffect(() => {
    let cancelled = false;
    get<{ suppliers: SupplierRow[] }>("/lab/suppliers")
      .then((r) => !cancelled && setSuppliers(r.suppliers))
      .catch((e: unknown) => !cancelled && setError(messageOf(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = useMemo<Row[]>(
    () =>
      (suppliers ?? []).map((s) => ({
        ...s,
        delay: value.delays[s.name] ?? 0,
        available: !value.unavailable.includes(s.name),
      })),
    [suppliers, value]
  );

  const columns = useMemo<ColDef<Row>[]>(() => {
    const info: ColDef<Row>[] = [
      {
        field: "name",
        headerName: "Supplier",
        minWidth: narrow ? 118 : 200,
        cellRenderer: (p: ICellRendererParams<Row>) =>
          p.data && (
            <div className="grid-name">
              <strong>{p.data.name}</strong>
              {p.data.only_option_for.length > 0 ? (
                <span className="warn-text">Only option for {p.data.only_option_for.join(", ")}</span>
              ) : (
                <span>Supplies {plural(p.data.items.length, "item")}</span>
              )}
            </div>
          ),
      },
      {
        field: "fastest_lead_days",
        headerName: "Delivers in",
        flex: 1,
        minWidth: 120,
        valueFormatter: (p) => plural(p.value as number, "day"),
      },
      {
        colId: "reliability",
        headerName: "Reliability",
        flex: 1,
        minWidth: 150,
        valueGetter: (p) => p.data?.reliability ?? null,
        valueFormatter: (p) => (p.data ? reliabilityText(p.data) : ""),
      },
    ];
    const controls: ColDef<Row>[] = [
      {
        field: "delay",
        headerName: "Extra delay",
        flex: 1,
        minWidth: narrow ? 96 : 140,
        editable: true,
        singleClickEdit: true,
        cellEditor: "agNumberCellEditor",
        cellEditorParams: { min: 0, max: 14, precision: 0, step: 1 },
        valueParser: (p) => {
          const n = Math.round(Number(p.newValue));
          return Number.isFinite(n) ? Math.min(14, Math.max(0, n)) : p.oldValue;
        },
        cellClass: (p) => (p.data?.delay ? "edit-cell changed" : "edit-cell"),
        valueFormatter: (p) => (p.value ? `+${plural(p.value as number, "day")}` : "On time"),
      },
      {
        field: "available",
        headerName: "Available",
        flex: 1,
        minWidth: narrow ? 84 : 110,
        editable: true,
        singleClickEdit: true,
        cellRenderer: "agCheckboxCellRenderer",
        cellEditor: "agCheckboxCellEditor",
        cellClass: (p) => (p.data?.available === false ? "edit-cell changed" : "edit-cell"),
      },
    ];
    // Phone: supplier name and the two editable columns first, the rest to the right.
    if (narrow) return [info[0], ...controls, ...info.slice(1)];
    return [{ ...info[0], pinned: "left" }, ...info.slice(1), ...controls];
  }, [narrow]);

  function edited(e: CellValueChangedEvent<Row>) {
    const row = e.data;
    if (!row) return;
    const delays = { ...value.delays };
    if (row.delay > 0) delays[row.name] = row.delay;
    else delete delays[row.name];
    const unavailable = value.unavailable.filter((n) => n !== row.name);
    if (!row.available) unavailable.push(row.name);
    onChange({ ...value, delays, unavailable });
  }

  const active = stressIsActive(value);
  const lines: string[] = [];
  if (applied?.active) {
    if (applied.demand_change_pct !== 0) {
      lines.push(`Usage ${applied.demand_change_pct > 0 ? "+" : ""}${applied.demand_change_pct}%`);
    }
    for (const n of applied.unavailable_suppliers) lines.push(`${n} unavailable`);
    for (const [n, d] of Object.entries(applied.supplier_delays)) {
      if (!applied.unavailable_suppliers.includes(n)) lines.push(`${n} ${plural(d, "day")} late`);
    }
  }

  return (
    <section className="panel" aria-labelledby="stress-title">
      <div className="panel-head">
        <h2 id="stress-title">Stress test</h2>
        <p className="hint">What if a supplier lets you down, or you sell more than usual?</p>
      </div>

      <div className="stress-controls">
        <label>
          Usage is
          <select value={value.demandPct} onChange={(e) => onChange({ ...value, demandPct: Number(e.target.value) })}>
            {DEMAND.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </label>
        <button disabled={!active || busy} onClick={() => onChange(NO_STRESS)}>
          Reset what-ifs
        </button>
      </div>

      {error && (
        <p className="error-box" role="alert">
          {error}
        </p>
      )}
      {!suppliers && !error && <p className="hint">Loading suppliers…</p>}
      {suppliers && (
        <>
          <p className="hint grid-legend">Click a highlighted cell to change it. The strategies below update right away.</p>
          <div className="grid-wrap" role="region" aria-label="Supplier stress test">
            <AgGridReact<Row>
              {...gridDefaults}
              rowData={rows}
              columnDefs={columns}
              getRowId={(p) => p.data.name}
              onCellValueChanged={edited}
              defaultColDef={{ sortable: false, resizable: false, suppressHeaderMenuButton: true }}
            />
          </div>
        </>
      )}
      <p className="hint" role="status" aria-live="polite">
        {lines.length > 0
          ? `Applied to the strategies below: ${lines.join(", ")}.`
          : "No what-ifs applied. The strategies below use today's usage and normal delivery times."}
      </p>
    </section>
  );
}
