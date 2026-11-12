import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import type { CellClickedEvent, ColDef, ICellRendererParams, IHeaderParams } from "ag-grid-community";

import { gridDefaults } from "../grid/setup";
import { useNarrow } from "../grid/useNarrow";
import { money, plural } from "../format";
import type { Scenario } from "../types";

export const STRATEGY_NAMES: Record<string, string> = {
  all_cheapest: "Everything, cheapest",
  all_fastest: "Everything, fastest",
  critical_only: "Critical items only",
  fit_budget: "Fit the budget",
};

type Cell =
  | { kind: "buy"; supplier: string; total: number; arrives: number; risk: string | null }
  | { kind: "wait"; text: string; risk: string | null }
  | { kind: "none" }
  | { kind: "sum"; main: string; bad?: boolean };

type Row = { item: string; cells: Record<string, Cell> };

function riskText(s: Scenario, item: string): string | null {
  const e = s.exposed.find((x) => x.item === item);
  if (!e) return null;
  return e.stockout_days === null ? "No supplier left" : `${plural(e.stockout_days, "day")} without stock`;
}

function cellFor(s: Scenario, item: string): Cell {
  const risk = riskText(s, item);
  const bought = s.bought.find((l) => l.item === item);
  if (bought) return { kind: "buy", supplier: bought.supplier, total: bought.total, arrives: bought.arrives_in_days, risk };
  const waits = s.deferred.find((d) => d.item === item);
  if (waits) {
    const text = waits.can_wait
      ? waits.order_within_days === null
        ? "Can wait"
        : `Can wait, order within ${plural(waits.order_within_days, "day")}`
      : "Not ordered";
    return { kind: "wait", text, risk };
  }
  return risk ? { kind: "wait", text: "Not ordered", risk } : { kind: "none" };
}

function MatrixCell({ cell }: { cell: Cell }) {
  if (cell.kind === "none") return <span className="matrix-none">Not needed</span>;
  if (cell.kind === "sum") return <strong className={cell.bad ? "bad" : ""}>{cell.main}</strong>;
  return (
    <div className="matrix-cell">
      {cell.kind === "buy" ? (
        <>
          <strong>{cell.supplier}</strong>
          <span>
            {money(cell.total)}, arrives in {plural(cell.arrives, "day")}
          </span>
        </>
      ) : (
        <span className="matrix-wait">{cell.text}</span>
      )}
      {cell.risk && <span className="bad">{cell.risk}</span>}
    </div>
  );
}

type HeaderExtra = { strategy: string; recommended: boolean; selected: boolean; onSelect: (key: string) => void };

function StrategyHeader(props: IHeaderParams & HeaderExtra) {
  return (
    <button className="matrix-head" aria-pressed={props.selected} onClick={() => props.onSelect(props.strategy)}>
      <span>{props.displayName}</span>
      {props.recommended && <span className="badge pick">Recommended</span>}
    </button>
  );
}

type Props = {
  scenarios: Scenario[];
  recommended: string;
  selected: string;
  budget: number;
  onSelect: (key: string) => void;
};

/**
 * Items down the side, strategies across the top. Each cell says what that strategy does with
 * that item, so you can see where the strategies differ instead of only comparing totals.
 */
export function DecisionMatrix({ scenarios, recommended, selected, budget, onSelect }: Props) {
  const narrow = useNarrow();
  const rows = useMemo<Row[]>(() => {
    const names = new Set<string>();
    for (const s of scenarios) {
      s.bought.forEach((l) => names.add(l.item));
      s.deferred.forEach((d) => names.add(d.item));
      s.exposed.forEach((e) => names.add(e.item));
    }
    const boughtIn = (item: string) => scenarios.filter((s) => s.bought.some((l) => l.item === item)).length;
    return [...names]
      .sort((a, b) => boughtIn(b) - boughtIn(a) || a.localeCompare(b))
      .map((item) => ({ item, cells: Object.fromEntries(scenarios.map((s) => [s.key, cellFor(s, item)])) }));
  }, [scenarios]);

  const totals = useMemo<Row[]>(
    () => [
      {
        item: "Total spend",
        cells: Object.fromEntries(
          scenarios.map((s) => [
            s.key,
            { kind: "sum", main: s.over_budget ? `${money(s.spend)}, over by ${money(s.spend - budget)}` : money(s.spend), bad: s.over_budget } as Cell,
          ])
        ),
      },
      {
        item: "Stockout risk",
        cells: Object.fromEntries(
          scenarios.map((s) => [
            s.key,
            {
              kind: "sum",
              main: s.exposed.length === 0 ? "None expected" : `${plural(s.exposed.length, "item")} may run out`,
              bad: s.exposed.length > 0,
            } as Cell,
          ])
        ),
      },
    ],
    [scenarios, budget]
  );

  const columns = useMemo<ColDef<Row>[]>(
    () => [
      {
        field: "item",
        headerName: "Item",
        pinned: "left",
        width: narrow ? 104 : 140,
        cellRenderer: (p: ICellRendererParams<Row>) => <strong>{p.value}</strong>,
      },
      ...scenarios.map<ColDef<Row>>((s) => ({
        colId: s.key,
        headerName: STRATEGY_NAMES[s.key] ?? s.name,
        flex: 1,
        minWidth: narrow ? 176 : 190,
        valueGetter: (p) => p.data?.cells[s.key],
        headerComponent: StrategyHeader,
        headerComponentParams: { strategy: s.key, recommended: s.key === recommended, selected: s.key === selected, onSelect },
        headerClass: s.key === selected ? "col-selected" : "",
        cellClass: s.key === selected ? "col-selected" : "",
        cellRenderer: (p: ICellRendererParams<Row, Cell>) => (p.value ? <MatrixCell cell={p.value} /> : null),
        getQuickFilterText: () => "",
      })),
    ],
    [scenarios, recommended, selected, onSelect, narrow]
  );

  function clicked(e: CellClickedEvent<Row>) {
    const key = e.colDef.colId;
    if (key && scenarios.some((s) => s.key === key)) onSelect(key);
  }

  return (
    <div className="grid-wrap matrix" role="region" aria-label="What each strategy does with each item">
      <AgGridReact<Row>
        {...gridDefaults}
        rowData={rows}
        columnDefs={columns}
        getRowId={(p) => p.data.item}
        pinnedBottomRowData={totals}
        rowHeight={72}
        headerHeight={60}
        onCellClicked={clicked}
        defaultColDef={{ sortable: false, resizable: false, suppressHeaderMenuButton: true }}
      />
    </div>
  );
}
