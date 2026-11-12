import { useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, ICellRendererParams, IRowNode } from "ag-grid-community";

import { get, messageOf } from "../api";
import { gridDefaults } from "../grid/setup";
import { money, plural } from "../format";
import type { Purchase } from "../types";

type Source = "all" | "real" | "demo";

type Summary = { item: string; total: number; qty: number };

function dateText(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/**
 * Every purchase behind the spending charts. The total under the table always matches the rows
 * you are looking at, so a filtered view can be checked against the charts above.
 */
export function LedgerGrid() {
  const gridRef = useRef<AgGridReact<Purchase>>(null);
  const [rows, setRows] = useState<Purchase[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [source, setSource] = useState<Source>("all");
  const [shown, setShown] = useState<{ count: number; total: number }>({ count: 0, total: 0 });

  useEffect(() => {
    let cancelled = false;
    get<{ purchases: Purchase[] }>("/purchases")
      .then((r) => !cancelled && setRows(r.purchases))
      .catch((e: unknown) => !cancelled && setError(messageOf(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  const columns = useMemo<ColDef<Purchase>[]>(
    () => [
      {
        field: "purchased_on",
        headerName: "Date",
        width: 140,
        initialSort: "desc",
        valueFormatter: (p) => (p.node?.rowPinned ? "" : dateText(p.value as string)),
      },
      {
        field: "item",
        headerName: "Item",
        getQuickFilterText: (p) => (p.data ? `${p.data.item} ${p.data.category}` : ""),
        minWidth: 150,
        flex: 1,
        cellRenderer: (p: ICellRendererParams<Purchase>) =>
          p.data && !p.node.rowPinned ? (
            <div className="grid-name">
              <strong>{p.data.item}</strong>
              <span>{p.data.category}</span>
            </div>
          ) : (
            <strong>{p.value}</strong>
          ),
      },
      { field: "supplier", headerName: "Supplier", minWidth: 140, flex: 1 },
      {
        field: "qty",
        headerName: "Quantity",
        width: 120,
        type: "rightAligned",
        valueFormatter: (p) => (p.node?.rowPinned ? "" : String(p.value)),
      },
      {
        field: "total",
        headerName: "Total",
        width: 130,
        type: "rightAligned",
        valueFormatter: (p) => money(p.value as number),
      },
      {
        field: "is_demo",
        headerName: "Source",
        width: 150,
        valueFormatter: (p) => (p.node?.rowPinned ? "" : p.value ? "Demo data" : "Real order"),
        cellRenderer: (p: ICellRendererParams<Purchase>) =>
          p.data && !p.node.rowPinned ? (
            <span className={`badge ${p.data.is_demo ? "demo" : "ok"}`}>{p.data.is_demo ? "Demo data" : "Real order"}</span>
          ) : null,
      },
    ],
    []
  );

  const pinned = useMemo<Summary[]>(
    () => [{ item: `Total of ${plural(shown.count, "purchase")} shown`, total: shown.total, qty: 0 }],
    [shown]
  );

  function recount() {
    const api = gridRef.current?.api;
    if (!api) return;
    let count = 0;
    let total = 0;
    api.forEachNodeAfterFilter((node: IRowNode<Purchase>) => {
      if (node.data) {
        count += 1;
        total += node.data.total;
      }
    });
    total = Math.round(total * 100) / 100;
    setShown((prev) => (prev.count === count && prev.total === total ? prev : { count, total }));
  }

  if (error) {
    return (
      <p className="error-box" role="alert">
        {error}
      </p>
    );
  }
  if (!rows) return <p className="hint">Loading purchases…</p>;

  const realCount = rows.filter((r) => !r.is_demo).length;

  return (
    <>
      <div className="grid-tools">
        <label className="grid-search">
          <span className="sr-only">Search purchases</span>
          <input
            type="search"
            placeholder="Search item, supplier or category"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </label>
        <div className="segmented" role="group" aria-label="Purchase source">
          <button aria-pressed={source === "all"} onClick={() => setSource("all")}>
            All
          </button>
          <button aria-pressed={source === "real"} onClick={() => setSource("real")}>
            Real orders ({realCount})
          </button>
          <button aria-pressed={source === "demo"} onClick={() => setSource("demo")}>
            Demo data
          </button>
        </div>
        <button onClick={() => gridRef.current?.api.exportDataAsCsv({ fileName: "rescuebuy-purchases.csv", skipPinnedBottom: true })}>
          Export CSV
        </button>
      </div>
      <div className="grid-wrap" role="region" aria-label="Purchase ledger">
        <AgGridReact<Purchase>
          ref={gridRef}
          {...gridDefaults}
          rowData={rows}
          columnDefs={columns}
          quickFilterText={filter}
          isExternalFilterPresent={() => source !== "all"}
          doesExternalFilterPass={(node) => (source === "real" ? !node.data?.is_demo : source === "demo" ? !!node.data?.is_demo : true)}
          onFilterChanged={recount}
          onModelUpdated={recount}
          pagination
          paginationPageSize={10}
          paginationPageSizeSelector={false}
          rowHeight={52}
          pinnedBottomRowData={pinned as unknown as Purchase[]}
          defaultColDef={{ sortable: true, resizable: false, suppressHeaderMenuButton: true }}
          overlayNoRowsTemplate="No purchases match."
        />
      </div>
    </>
  );
}
