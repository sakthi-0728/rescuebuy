"""A read-only picture of the business at one moment, loaded once per question."""
from dataclasses import dataclass
from datetime import date

from app import db
from app.analytics import budget_status, last_months, spent_in_month
from app.inventory import Item, item_view
from app.lab import Candidate, build_candidates
from app.orders import Order
from app.policy import Policy
from app.suppliers import Supplier


def build_views(conn) -> list[dict]:
    buffer_days = db.get_settings(conn)["buffer_days"]
    today = date.today()
    open_orders = db.open_orders_by_item(conn)
    views = []
    for item in db.load_items(conn):
        view = item_view(item, db.fastest_lead_time(conn, item.name), buffer_days, today)
        order = open_orders.get(item.name)
        view["open_order"] = {"id": order.id, "status": order.status.value} if order else None
        views.append(view)
    return views


@dataclass
class Snapshot:
    items: list[Item]
    views: list[dict]
    offers: dict[str, list[Supplier]]
    policy: Policy
    buffer_days: float
    purchases: list[dict]
    settings: dict
    orders: list[Order]
    today: date

    def view(self, name: str) -> dict | None:
        return next((v for v in self.views if v["item"] == name), None)

    def item(self, name: str) -> Item | None:
        return next((i for i in self.items if i.name == name), None)

    def budget(self) -> dict:
        month = last_months(self.today, 1)[0]
        spent = spent_in_month(self.purchases, month)
        return budget_status(self.settings["monthly_budget"], spent, month)

    def candidates(self) -> tuple[list[Candidate], list[str]]:
        return build_candidates(self.items, self.offers, self.policy, self.buffer_days)


def load_snapshot(conn) -> Snapshot:
    items = db.load_items(conn)
    settings = db.get_settings(conn)
    return Snapshot(
        items=items,
        views=build_views(conn),
        offers={i.name: db.load_offers(conn, i.name) for i in items},
        policy=db.load_policy(conn),
        buffer_days=settings["buffer_days"],
        purchases=db.load_purchases(conn),
        settings=settings,
        orders=db.list_orders(conn),
        today=date.today(),
    )
