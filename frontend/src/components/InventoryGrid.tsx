import { useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";

import { gridDefaults } from "../grid/setup";
import { RunwayCell } from "../grid/RunwayCell";
import { expiryText, money, riskLabel } from "../format";
import type { ItemRow, Risk } from "../types";

type Props = {
  items: ItemRow[];
  busy: boolean;
  onReview: (item: string) => void;
};

const RANK: Record<Risk, number> = { critical: 0, warning: 1, ok: 2 };

/** Most urgent first: risk band, then fewest days of stock. */
function urgency(row: ItemRow): number {
  return RANK[row.risk] * 1000 + (row.days_left ?? 999);
}

function nullsLast(a: number | null | undefined, b: number | null | undefined): number {
  const x = a ?? Number.POSITIVE_INFINITY;
  const y = b ?? Number.POSITIVE_INFINITY;
  return x === y ? 0 : x < y ? -1 : 1;
}

type Pinned = { item: string; inventory_value: number };

/**
 * The inventory as a runway board. Each bar is days of stock left and the tick is the fastest
 * delivery, so the gap between them is the margin. Sorting, filtering and CSV export come from
 * AG Grid Community.
 */
export function InventoryGrid({ items, busy, onReview }: Props) {
  const gridRef = useRef<AgGridReact<ItemRow>>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState("");
  const [width, setWidth] = useState(1100);

  // On a narrower panel the secondary columns are dropped so "Review reorder" stays on screen.
  // The same facts are on the cards view.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    setWidth(el.clientWidth);
    return () => observer.disconnect();
  }, []);
  const compact = width < 900;

  const columns = useMemo<ColDef<ItemRow>[]>(() => {
    const all: ColDef<ItemRow>[] = [
      {
        colId: "urgency",
        hide: true,
        valueGetter: (p) => (p.data ? urgency(p.data) : 0),
        initialSort: "asc",
      },
      {
        field: "item",
        headerName: "Item",
        pinned: "left",
        getQuickFilterText: (p) => (p.data ? `${p.data.item} ${p.data.category}` : ""),
        minWidth: 150,
        cellRenderer: (p: ICellRendererParams<ItemRow>) =>
          p.data && !p.node.rowPinned ? (
            <div className="grid-name">
              <strong>{p.data.item}</strong>
              <span>
                {p.data.category} · {p.data.stock} {p.data.unit}
              </span>
            </div>
          ) : (
            <strong>{p.value}</strong>
          ),
      },
      {
        colId: "runway",
        headerName: "Runway",
        flex: 2,
        minWidth: 200,
        valueGetter: (p) => p.data?.days_left ?? null,
        comparator: nullsLast,
        cellRenderer: (p: ICellRendererParams<ItemRow>) => (p.data && !p.node.rowPinned ? <RunwayCell row={p.data} /> : null),
      },
      {
        field: "risk",
        headerName: "Status",
        width: 108,
        comparator: (a: Risk, b: Risk) => RANK[a] - RANK[b],
        getQuickFilterText: (p) => riskLabel(p.value as Risk),
        cellRenderer: (p: ICellRendererParams<ItemRow>) =>
          p.data && !p.node.rowPinned ? <span className={`badge ${p.data.risk}`}>{riskLabel(p.data.risk)}</span> : null,
      },
      {
        field: "daily_usage",
        headerName: "Used per day",
        width: 124,
        type: "rightAligned",
        valueFormatter: (p) => (p.node?.rowPinned || !p.data ? "" : `${p.value} ${p.data.unit}`),
      },
      {
        field: "days_to_expiry",
        headerName: "Expiry",
        width: 128,
        comparator: nullsLast,
        valueFormatter: (p) => (p.node?.rowPinned ? "" : expiryText(p.value as number | null)),
      },
      {
        field: "inventory_value",
        headerName: "Stock value",
        width: 118,
        type: "rightAligned",
        valueFormatter: (p) => money(p.value as number),
      },
      {
        colId: "action",
        headerName: "",
        width: 176,
        sortable: false,
        cellRenderer: (p: ICellRendererParams<ItemRow>) => {
          const row = p.data;
          if (!row || p.node.rowPinned) return null;
          if (row.open_order) return <span className="in-progress">Order {row.open_order.id} in progress</span>;
          return (
            <button disabled={busy} className={row.risk === "ok" ? "" : "primary"} onClick={() => onReview(row.item)}>
              Review reorder
            </button>
          );
        },
      },
    ];
    const hidden = new Set(compact ? ["daily_usage", "days_to_expiry", "inventory_value"] : []);
    return all.filter((c) => !(c.field && hidden.has(c.field)));
  }, [busy, onReview, compact]);

  const pinned = useMemo<Pinned[]>(
    () => [{ item: "Total stock value", inventory_value: items.reduce((sum, r) => sum + r.inventory_value, 0) }],
    [items]
  );

  function exportCsv() {
    gridRef.current?.api.exportDataAsCsv({
      fileName: "rescuebuy-inventory.csv",
      columnKeys: ["item", "runway", "risk", "daily_usage", "days_to_expiry", "inventory_value"],
      skipPinnedBottom: true,
    });
  }

  return (
    <>
      <div className="grid-tools">
        <label className="grid-search">
          <span className="sr-only">Search inventory</span>
          <input
            type="search"
            placeholder="Search items, categories or status"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </label>
        <button onClick={exportCsv}>Export CSV</button>
      </div>
      <p className="hint grid-legend">
        Each bar is the days of stock left. The tick is the fastest delivery. When the bar ends before the tick, the
        shelf empties first. Select a column heading to sort.
      </p>
      <div className="grid-wrap" ref={wrapRef} role="region" aria-label="Inventory runway board">
        <AgGridReact<ItemRow>
          ref={gridRef}
          {...gridDefaults}
          rowData={items}
          columnDefs={columns}
          getRowId={(p) => p.data.item}
          quickFilterText={filter}
          pinnedBottomRowData={pinned as unknown as ItemRow[]}
          defaultColDef={{ sortable: true, resizable: false, suppressHeaderMenuButton: true }}
          overlayNoRowsTemplate="No items match your search."
        />
      </div>
    </>
  );
}
