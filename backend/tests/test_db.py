import sqlite3

import pytest

from app import db
from app.orders import Status


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RESCUEBUY_DB", str(tmp_path / "test.db"))
    db.init_db(force=True)


def test_demo_data_is_seeded():
    with db.connect() as conn:
        items = db.load_items(conn)
    assert [i.name for i in items][:3] == ["Bakery boxes", "Flour", "Butter"]
    assert len(items) == 8


def test_only_perishables_have_expiry_dates():
    with db.connect() as conn:
        items = {i.name: i for i in db.load_items(conn)}
    assert items["Butter"].expiry_date is not None
    assert items["Eggs"].expiry_date is not None
    assert items["Flour"].expiry_date is None


def test_offers_include_fee_minimum_and_stock():
    with db.connect() as conn:
        offers = {s.name: s for s in db.load_offers(conn, "Bakery boxes")}
    assert offers["QuickPack"].min_order_qty == 200
    assert offers["QuickPack"].delivery_fee == 10
    assert offers["BakersChoice"].stock_available == 3000
    assert offers["Shady Traders"].approved is False


def test_reliability_comes_from_delivery_history():
    with db.connect() as conn:
        offers = {s.name: s for s in db.load_offers(conn, "Bakery boxes")}
    assert offers["BakersChoice"].reliability == 0.9   # 9 of 10 on time
    assert offers["BakersChoice"].history_count == 10


def test_reliability_is_unknown_without_enough_history():
    with db.connect() as conn:
        offers = {s.name: s for s in db.load_offers(conn, "Bakery boxes")}
    assert offers["QuickPack"].reliability is None     # only 2 deliveries
    assert offers["Shady Traders"].reliability is None  # none at all
    assert offers["Shady Traders"].history_count == 0


def test_fastest_lead_time_ignores_unapproved_suppliers():
    with db.connect() as conn:
        assert db.fastest_lead_time(conn, "Bakery boxes") == 1


def test_policy_is_loaded_from_settings():
    with db.connect() as conn:
        policy = db.load_policy(conn)
    assert policy.max_auto_spend == 150
    assert policy.budget == 1500


def test_order_round_trip_keeps_timeline():
    with db.connect() as conn:
        created = db.create_order(conn, "Flour", "FreshMart", 50, 62.5)
    with db.connect() as conn:
        loaded = db.get_order(conn, created.id)
    assert loaded.status == Status.PENDING_APPROVAL
    assert loaded.item == "Flour"
    assert [e["type"] for e in loaded.timeline] == ["ORDER_CREATED"]


def test_orders_survive_a_restart_but_a_reset_clears_them():
    with db.connect() as conn:
        db.create_order(conn, "Flour", "FreshMart", 50, 62.5)
    db.init_db()  # what happens when the server starts again
    with db.connect() as conn:
        assert len(db.list_orders(conn)) == 1
    db.init_db(force=True)  # demo reset
    with db.connect() as conn:
        assert db.list_orders(conn) == []


def test_old_schema_is_rebuilt():
    conn = sqlite3.connect(db.db_path())
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    db.init_db()
    with db.connect() as conn:
        assert len(db.load_items(conn)) == 8


def test_open_order_lookup_ignores_finished_orders():
    with db.connect() as conn:
        order = db.create_order(conn, "Flour", "FreshMart", 50, 62.5)
        assert db.open_order_for_item(conn, "Flour").id == order.id
        order.status = Status.REJECTED
        db.save_order(conn, order)
        assert db.open_order_for_item(conn, "Flour") is None
        assert db.count_open_orders(conn) == 0


def test_add_stock_and_webhook_dedupe():
    with db.connect() as conn:
        db.add_stock(conn, "Flour", 50)
        assert db.get_item(conn, "Flour").stock == 170
        assert db.record_webhook_event(conn, "WH-1", "X", "s") is True
        assert db.record_webhook_event(conn, "WH-1", "X", "s") is False
        assert len(db.list_webhook_events(conn)) == 1


def test_open_orders_are_grouped_by_item():
    with db.connect() as conn:
        a = db.create_order(conn, "Flour", "FreshMart", 50, 62.5)
        b = db.create_order(conn, "Butter", "FreshMart", 36, 259.8)
        b.status = Status.REJECTED
        db.save_order(conn, b)
        found = db.open_orders_by_item(conn)
    assert list(found) == ["Flour"]
    assert found["Flour"].id == a.id


# ---- Purchase history ----

def test_demo_history_covers_six_months_and_is_labelled_demo():
    with db.connect() as conn:
        purchases = db.load_purchases(conn)
    assert len(purchases) == 72
    assert all(p["is_demo"] for p in purchases)
    assert len({p["purchased_on"][:7] for p in purchases}) == 6


def test_no_purchase_is_dated_in_the_future():
    from datetime import date

    with db.connect() as conn:
        latest = max(p["purchased_on"] for p in db.load_purchases(conn))
    assert latest <= date.today().isoformat()


@pytest.mark.parametrize("day", [1, 2, 9, 15, 27, 28])
def test_this_months_demo_purchases_are_never_future_or_identical_rows(day):
    """Early in the month, purchases are spread over the days so far, not piled onto one date."""
    from datetime import date

    today = date(2026, 11, day)
    with db.connect() as conn:
        conn.execute("DELETE FROM purchases")
        db._seed_purchases(conn, today)
        rows = [p for p in db.load_purchases(conn) if p["purchased_on"].startswith("2026-11")]
    assert rows and max(p["purchased_on"] for p in rows) <= today.isoformat()
    if day >= 9:
        keys = [(p["item"], p["purchased_on"]) for p in rows]
        assert len(keys) == len(set(keys)), "the same item should not be bought twice on one date"


def test_a_real_purchase_is_recorded_with_its_category():
    with db.connect() as conn:
        db.record_purchase(conn, "Butter", "FreshMart", 36, 259.8)
        last = db.load_purchases(conn)[-1]
    assert last["category"] == "Dairy"
    assert last["is_demo"] is False
    assert last["total"] == 259.8


def test_reset_drops_real_purchases_and_restores_the_demo_history():
    with db.connect() as conn:
        db.record_purchase(conn, "Butter", "FreshMart", 36, 259.8)
    db.init_db(force=True)
    with db.connect() as conn:
        purchases = db.load_purchases(conn)
    assert len(purchases) == 72
    assert all(p["is_demo"] for p in purchases)


def test_create_order_keeps_the_decision_record_on_the_first_event():
    with db.connect() as conn:
        order = db.create_order(conn, "Flour", "FreshMart", 50, 62.5, record={"reason": "test"})
        again = db.get_order(conn, order.id)
    assert again.timeline[0]["type"] == "ORDER_CREATED"
    assert again.timeline[0]["record"] == {"reason": "test"}


def test_create_order_without_a_record_adds_none():
    with db.connect() as conn:
        order = db.create_order(conn, "Flour", "FreshMart", 50, 62.5)
    assert "record" not in order.timeline[0]


def test_events_are_found_by_resource_id_and_ignore_empty_ids():
    with db.connect() as conn:
        db.record_webhook_event(conn, "WH-1", "A", "first", "AUTH1")
        db.record_webhook_event(conn, "WH-2", "B", "second", "CAP1")
        db.record_webhook_event(conn, "WH-3", "C", "no resource")
        assert [e["id"] for e in db.events_for_resources(conn, ["AUTH1", None, ""])] == ["WH-1"]
        assert [e["id"] for e in db.events_for_resources(conn, ["AUTH1", "CAP1"])] == ["WH-1", "WH-2"]
        assert db.events_for_resources(conn, [None, None]) == []
