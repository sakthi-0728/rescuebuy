"""SQLite storage. Plain sqlite3, no extra packages.

The database file is created and filled with labelled demo data on first start.
If SCHEMA_VERSION changes, the demo database is rebuilt automatically.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from app.inventory import Item
from app.orders import Order, Status
from app.policy import Policy
from app.suppliers import Supplier

SCHEMA_VERSION = 3
MIN_HISTORY = 3  # deliveries needed before a reliability figure is shown
OPEN_STATUSES = (
    Status.PENDING_APPROVAL.value,
    Status.APPROVED.value,
    Status.PAYMENT_STARTED.value,
    Status.AUTHORIZED.value,
)

SCHEMA = """
CREATE TABLE settings (key TEXT PRIMARY KEY, value REAL NOT NULL);
CREATE TABLE items (
    name TEXT PRIMARY KEY, category TEXT NOT NULL, unit TEXT NOT NULL,
    stock REAL NOT NULL, daily_usage REAL NOT NULL, incoming REAL NOT NULL DEFAULT 0,
    unit_cost REAL NOT NULL, criticality INTEGER NOT NULL DEFAULT 2,
    expiry_date TEXT, last_restocked TEXT
);
CREATE TABLE suppliers (
    name TEXT PRIMARY KEY, approved INTEGER NOT NULL DEFAULT 1,
    delivery_fee REAL NOT NULL DEFAULT 0
);
CREATE TABLE offers (
    supplier TEXT NOT NULL, item TEXT NOT NULL, unit_price REAL NOT NULL,
    lead_time_days REAL NOT NULL, min_order_qty INTEGER NOT NULL DEFAULT 1,
    stock_available INTEGER, PRIMARY KEY (supplier, item)
);
CREATE TABLE deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, supplier TEXT NOT NULL, item TEXT NOT NULL,
    ordered_qty INTEGER NOT NULL, received_qty INTEGER NOT NULL,
    on_time INTEGER NOT NULL, delivered_on TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT NOT NULL, supplier_name TEXT NOT NULL,
    qty INTEGER NOT NULL, total REAL NOT NULL, status TEXT NOT NULL,
    paypal_order_id TEXT, authorization_id TEXT, capture_id TEXT, authorized_at TEXT,
    timeline TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT NOT NULL, category TEXT NOT NULL,
    supplier TEXT NOT NULL, qty INTEGER NOT NULL, total REAL NOT NULL,
    purchased_on TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE webhook_events (
    id TEXT PRIMARY KEY, event_type TEXT, summary TEXT, received_at TEXT NOT NULL,
    resource_id TEXT
);
"""

# ---- Demo data (a small bakery). All of this is labelled as demo data in the app. ----

SETTINGS = {
    "max_auto_spend": 150,    # orders above this are flagged as large orders
    "order_budget": 1500,     # hard cap for a single order
    "monthly_budget": 2700,
    "buffer_days": 3,
}

# name, category, unit, stock, daily_usage, incoming, unit_cost, criticality, days until expiry
DEMO_ITEMS = [
    ("Bakery boxes", "Packaging", "boxes", 600, 200, 0, 0.45, 2, None),
    ("Flour", "Dry goods", "kg", 120, 40, 0, 0.90, 3, None),
    ("Butter", "Dairy", "kg", 12, 12, 0, 6.50, 3, 4),
    ("Eggs", "Dairy", "trays", 120, 10, 0, 4.80, 3, 6),
    ("Sugar", "Dry goods", "kg", 400, 15, 0, 1.05, 2, None),
    ("Yeast", "Dry goods", "kg", 3, 1, 0, 8.00, 2, None),
    ("Paper bags", "Packaging", "bags", 450, 150, 0, 0.08, 1, None),
    ("Cocoa powder", "Dry goods", "kg", 120, 2, 0, 7.50, 1, None),
]

DEMO_SUPPLIERS = [  # name, approved, delivery fee
    ("FreshMart", 1, 15),
    ("BakersChoice", 1, 20),
    ("QuickPack", 1, 10),
    ("Budget Bulk", 1, 40),
    ("Shady Traders", 0, 0),
]

# supplier, item, unit price, lead time days, minimum order, quantity available
DEMO_OFFERS = [
    ("QuickPack", "Bakery boxes", 0.50, 1, 200, 5000),
    ("BakersChoice", "Bakery boxes", 0.45, 2, 300, 3000),
    ("Budget Bulk", "Bakery boxes", 0.38, 5, 1000, 20000),
    ("Shady Traders", "Bakery boxes", 0.30, 1, 100, 9000),
    ("FreshMart", "Flour", 0.95, 1, 200, 2000),
    ("BakersChoice", "Flour", 0.88, 2, 100, 1000),
    ("Budget Bulk", "Flour", 0.70, 5, 500, 10000),
    ("FreshMart", "Butter", 6.80, 1, 10, 200),
    ("BakersChoice", "Butter", 6.30, 2, 20, 15),
    ("FreshMart", "Eggs", 4.90, 1, 10, 300),
    ("BakersChoice", "Eggs", 4.60, 2, 20, 500),
    ("FreshMart", "Sugar", 1.15, 1, 25, 1000),
    ("BakersChoice", "Sugar", 1.05, 2, 50, 2000),
    ("Budget Bulk", "Sugar", 0.85, 5, 200, 8000),
    ("FreshMart", "Yeast", 8.20, 1, 10, 50),
    ("BakersChoice", "Yeast", 7.60, 2, 5, 40),
    ("QuickPack", "Paper bags", 0.09, 1, 500, 20000),
    ("Budget Bulk", "Paper bags", 0.06, 5, 2000, 50000),
    ("FreshMart", "Cocoa powder", 7.90, 1, 10, 100),
    ("BakersChoice", "Cocoa powder", 7.40, 2, 20, 80),
]

# supplier, number of past deliveries, how many arrived on time (demo history)
DEMO_HISTORY = [
    ("FreshMart", 12, 11),
    ("BakersChoice", 10, 9),
    ("Budget Bulk", 6, 4),
    ("QuickPack", 2, 2),  # too little history: shown as unknown
]


# One typical month of purchasing: day of month, item, category, supplier, quantity, total.
DEMO_PURCHASE_PATTERN = [
    (3, "Bakery boxes", "Packaging", "BakersChoice", 400, 200.00),
    (9, "Butter", "Dairy", "FreshMart", 36, 259.80),
    (12, "Flour", "Dry goods", "BakersChoice", 100, 108.00),
    (15, "Butter", "Dairy", "FreshMart", 36, 259.80),
    (18, "Eggs", "Dairy", "FreshMart", 40, 211.00),
    (20, "Bakery boxes", "Packaging", "BakersChoice", 400, 200.00),
    (22, "Butter", "Dairy", "FreshMart", 36, 259.80),
    (24, "Sugar", "Dry goods", "BakersChoice", 150, 177.50),
    (25, "Flour", "Dry goods", "BakersChoice", 100, 108.00),
    (26, "Cocoa powder", "Dry goods", "FreshMart", 30, 252.00),
    (27, "Paper bags", "Packaging", "QuickPack", 1500, 145.00),
    (28, "Yeast", "Dry goods", "FreshMart", 10, 97.00),
]
# Month-to-month variation for the demo history (months ago -> factor). This month is exact.
DEMO_MONTH_FACTORS = {5: 0.94, 4: 1.03, 3: 0.97, 2: 1.06, 1: 1.01, 0: 1.0}


def db_path() -> str:
    default = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rescuebuy.db")
    return os.getenv("RESCUEBUY_DB", default)


@contextmanager
def connect():
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _month_start(today: date, months_ago: int) -> date:
    year, month = today.year, today.month - months_ago
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _seed_purchases(conn: sqlite3.Connection, today: date) -> None:
    for months_ago, factor in DEMO_MONTH_FACTORS.items():
        start = _month_start(today, months_ago)
        for day, item, category, supplier, qty, total in DEMO_PURCHASE_PATTERN:
            # This month, nothing may be dated in the future. Purchases that would be are spread over
            # the days so far (rather than all piled onto today), so the ledger does not look duplicated.
            if months_ago == 0 and day > today.day:
                day = max(1, round(day * today.day / 28))
            conn.execute(
                "INSERT INTO purchases (item, category, supplier, qty, total, purchased_on, is_demo) "
                "VALUES (?,?,?,?,?,?,1)",
                (item, category, supplier, qty, round(total * factor, 2), start.replace(day=day).isoformat()),
            )


def _seed(conn: sqlite3.Connection) -> None:
    today = date.today()
    conn.executemany("INSERT INTO settings VALUES (?, ?)", SETTINGS.items())
    for name, cat, unit, stock, usage, incoming, cost, crit, expiry_days in DEMO_ITEMS:
        expiry = (today + timedelta(days=expiry_days)).isoformat() if expiry_days is not None else None
        conn.execute(
            "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, cat, unit, stock, usage, incoming, cost, crit, expiry,
             (today - timedelta(days=7)).isoformat()),
        )
    conn.executemany("INSERT INTO suppliers VALUES (?,?,?)", DEMO_SUPPLIERS)
    conn.executemany("INSERT INTO offers VALUES (?,?,?,?,?,?)", DEMO_OFFERS)

    offered = {}
    for supplier, item, *_ in DEMO_OFFERS:
        offered.setdefault(supplier, []).append(item)
    for supplier, n, on_time_count in DEMO_HISTORY:
        for i in range(n):
            item = offered[supplier][i % len(offered[supplier])]
            on_time = 1 if i < on_time_count else 0
            conn.execute(
                "INSERT INTO deliveries (supplier, item, ordered_qty, received_qty, on_time, delivered_on, is_demo) "
                "VALUES (?,?,?,?,?,?,1)",
                (supplier, item, 100, 100, on_time, (today - timedelta(days=7 * (i + 2))).isoformat()),
            )
    _seed_purchases(conn, today)


def init_db(force: bool = False) -> None:
    """Create the tables and demo data if needed. force=True rebuilds everything."""
    with connect() as conn:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        if not force and current == SCHEMA_VERSION:
            return
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for row in tables:
            conn.execute(f'DROP TABLE IF EXISTS "{row["name"]}"')
        conn.executescript(SCHEMA)
        _seed(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


# ---- Settings and policy ----

def get_settings(conn) -> dict:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def load_policy(conn) -> Policy:
    s = get_settings(conn)
    return Policy(max_auto_spend=s["max_auto_spend"], budget=s["order_budget"])


# ---- Items and suppliers ----

def _item_from_row(r) -> Item:
    return Item(
        name=r["name"], category=r["category"], unit=r["unit"], stock=r["stock"],
        daily_usage=r["daily_usage"], incoming=r["incoming"], unit_cost=r["unit_cost"],
        criticality=r["criticality"], expiry_date=r["expiry_date"],
        last_restocked=r["last_restocked"],
    )


def load_items(conn) -> list[Item]:
    return [_item_from_row(r) for r in conn.execute("SELECT * FROM items ORDER BY rowid")]


def get_item(conn, name: str) -> Item | None:
    r = conn.execute("SELECT * FROM items WHERE name = ?", (name,)).fetchone()
    return _item_from_row(r) if r else None


def supplier_stats(conn) -> dict[str, tuple[int, float]]:
    """supplier -> (deliveries on record, share that arrived on time)."""
    rows = conn.execute(
        "SELECT supplier, COUNT(*) AS n, SUM(on_time) AS on_time FROM deliveries GROUP BY supplier"
    )
    return {r["supplier"]: (r["n"], r["on_time"] / r["n"]) for r in rows}


def load_offers(conn, item_name: str) -> list[Supplier]:
    stats = supplier_stats(conn)
    rows = conn.execute(
        "SELECT o.supplier, o.unit_price, o.lead_time_days, o.min_order_qty, o.stock_available, "
        "s.approved, s.delivery_fee FROM offers o JOIN suppliers s ON s.name = o.supplier "
        "WHERE o.item = ? ORDER BY o.unit_price, o.lead_time_days",
        (item_name,),
    ).fetchall()
    suppliers = []
    for r in rows:
        n, rate = stats.get(r["supplier"], (0, 0.0))
        suppliers.append(
            Supplier(
                name=r["supplier"], unit_price=r["unit_price"], lead_time_days=r["lead_time_days"],
                approved=bool(r["approved"]), stock_available=r["stock_available"],
                reliability=round(rate, 2) if n >= MIN_HISTORY else None,
                min_order_qty=r["min_order_qty"], delivery_fee=r["delivery_fee"], history_count=n,
            )
        )
    return suppliers


def fastest_lead_time(conn, item_name: str) -> float | None:
    r = conn.execute(
        "SELECT MIN(o.lead_time_days) AS lead FROM offers o JOIN suppliers s ON s.name = o.supplier "
        "WHERE o.item = ? AND s.approved = 1",
        (item_name,),
    ).fetchone()
    return r["lead"]


def add_stock(conn, item_name: str, qty: float) -> None:
    conn.execute(
        "UPDATE items SET stock = stock + ?, last_restocked = ? WHERE name = ?",
        (qty, date.today().isoformat(), item_name),
    )


# ---- Orders ----

def _order_from_row(r) -> Order:
    return Order(
        id=r["id"], supplier_name=r["supplier_name"], qty=r["qty"], total=r["total"],
        status=Status(r["status"]), paypal_order_id=r["paypal_order_id"],
        authorization_id=r["authorization_id"], capture_id=r["capture_id"],
        authorized_at=r["authorized_at"], item=r["item"], timeline=json.loads(r["timeline"]),
    )


def save_order(conn, o: Order) -> None:
    conn.execute(
        "UPDATE orders SET status=?, paypal_order_id=?, authorization_id=?, capture_id=?, "
        "authorized_at=?, timeline=? WHERE id=?",
        (o.status.value, o.paypal_order_id, o.authorization_id, o.capture_id,
         o.authorized_at, json.dumps(o.timeline), o.id),
    )


def create_order(
    conn, item: str, supplier_name: str, qty: int, total: float, record: dict | None = None
) -> Order:
    """Create a proposed order. `record` is the decision record (why this order), kept on the
    first timeline event so it travels with the order."""
    cur = conn.execute(
        "INSERT INTO orders (item, supplier_name, qty, total, status, timeline, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (item, supplier_name, qty, total, Status.PENDING_APPROVAL.value, "[]",
         datetime.now(timezone.utc).isoformat()),
    )
    order = Order(id=cur.lastrowid, supplier_name=supplier_name, qty=qty, total=total, item=item)
    if record is not None:
        order.timeline[0]["record"] = record
    save_order(conn, order)
    return order


def get_order(conn, order_id: int) -> Order | None:
    r = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return _order_from_row(r) if r else None


def list_orders(conn) -> list[Order]:
    return [_order_from_row(r) for r in conn.execute("SELECT * FROM orders ORDER BY id")]


def find_order_by_paypal_id(conn, paypal_order_id: str) -> Order | None:
    r = conn.execute("SELECT * FROM orders WHERE paypal_order_id = ?", (paypal_order_id,)).fetchone()
    return _order_from_row(r) if r else None


def open_order_for_item(conn, item: str) -> Order | None:
    marks = ",".join("?" for _ in OPEN_STATUSES)
    r = conn.execute(
        f"SELECT * FROM orders WHERE item = ? AND status IN ({marks}) ORDER BY id LIMIT 1",
        (item, *OPEN_STATUSES),
    ).fetchone()
    return _order_from_row(r) if r else None


def open_orders_by_item(conn) -> dict[str, Order]:
    marks = ",".join("?" for _ in OPEN_STATUSES)
    rows = conn.execute(
        f"SELECT * FROM orders WHERE status IN ({marks}) ORDER BY id", OPEN_STATUSES
    )
    found: dict[str, Order] = {}
    for r in rows:
        found.setdefault(r["item"], _order_from_row(r))
    return found


def count_open_orders(conn) -> int:
    marks = ",".join("?" for _ in OPEN_STATUSES)
    return conn.execute(
        f"SELECT COUNT(*) FROM orders WHERE status IN ({marks})", OPEN_STATUSES
    ).fetchone()[0]


# ---- Purchases (spending history) ----

def record_purchase(conn, item_name: str, supplier: str, qty: int, total: float) -> None:
    """A real purchase: called only when delivery is confirmed and the payment is captured."""
    row = conn.execute("SELECT category FROM items WHERE name = ?", (item_name,)).fetchone()
    conn.execute(
        "INSERT INTO purchases (item, category, supplier, qty, total, purchased_on, is_demo) "
        "VALUES (?,?,?,?,?,?,0)",
        (item_name, row["category"] if row else "Other", supplier, qty, total, date.today().isoformat()),
    )


def load_purchases(conn) -> list[dict]:
    return [
        {
            "item": r["item"], "category": r["category"], "supplier": r["supplier"],
            "qty": r["qty"], "total": r["total"], "purchased_on": r["purchased_on"],
            "is_demo": bool(r["is_demo"]),
        }
        for r in conn.execute("SELECT * FROM purchases ORDER BY purchased_on, id")
    ]


# ---- Webhook events ----

def record_webhook_event(
    conn, event_id: str, event_type: str | None, summary: str | None, resource_id: str | None = None
) -> bool:
    """True if the event is new, False if it was already recorded. Only call this after the
    PayPal signature has been verified."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO webhook_events (id, event_type, summary, received_at, resource_id) "
        "VALUES (?,?,?,?,?)",
        (event_id, event_type, summary, datetime.now(timezone.utc).isoformat(), resource_id),
    )
    return cur.rowcount == 1


def list_webhook_events(conn) -> list[dict]:
    return [
        {"id": r["id"], "type": r["event_type"], "summary": r["summary"]}
        for r in conn.execute("SELECT * FROM webhook_events ORDER BY received_at, id")
    ]


def events_for_resources(conn, resource_ids: list[str]) -> list[dict]:
    """Verified PayPal events whose resource is one of the given PayPal ids (order, authorization
    or capture), oldest first. Matching happens when the order is read, so an event that arrives
    before the app has stored the id is still found later."""
    ids = [r for r in resource_ids if r]
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT * FROM webhook_events WHERE resource_id IN ({marks}) ORDER BY received_at, id", ids
    )
    return [
        {
            "id": r["id"], "type": r["event_type"], "summary": r["summary"],
            "resource_id": r["resource_id"], "time": r["received_at"],
        }
        for r in rows
    ]
