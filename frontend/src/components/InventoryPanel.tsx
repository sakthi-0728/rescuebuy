import { useState } from "react";

import type { ItemRow } from "../types";
import { InventoryCards } from "./InventoryCards";
import { InventoryGrid } from "./InventoryGrid";

type Props = {
  items: ItemRow[];
  busy: boolean;
  onReview: (item: string) => void;
};

type View = "board" | "cards";

/** The board suits a wide screen. A phone starts on cards, where nothing needs sideways scrolling. */
function startingView(): View {
  return window.matchMedia("(max-width: 720px)").matches ? "cards" : "board";
}

export function InventoryPanel({ items, busy, onReview }: Props) {
  const [view, setView] = useState<View>(startingView);
  return (
    <section className="panel" aria-labelledby="inventory-title">
      <div className="panel-head">
        <h2 id="inventory-title">Inventory runway</h2>
        <div className="segmented" role="group" aria-label="Inventory view">
          <button aria-pressed={view === "board"} onClick={() => setView("board")}>
            Board
          </button>
          <button aria-pressed={view === "cards"} onClick={() => setView("cards")}>
            Cards
          </button>
        </div>
      </div>
      {view === "board" ? (
        <InventoryGrid items={items} busy={busy} onReview={onReview} />
      ) : (
        <InventoryCards items={items} busy={busy} onReview={onReview} />
      )}
    </section>
  );
}
