import pytest

from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
from app.main import EVENTS, ORDERS, SEEN_EVENT_IDS, STOCK, app

client = TestClient(app)

BAKERY_BIG = {"stock": 600, "incoming": 0, "daily_usage": 200, "buffer_days": 3}


def setup_function():
    ORDERS.clear()
    STOCK["boxes"] = 600
    EVENTS.clear()
    SEEN_EVENT_IDS.clear()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_order_waits_for_approval():
    response = client.post("/orders", json=BAKERY_BIG)
    assert response.status_code == 200
    body = response.json()
    assert body["supplier_name"] == "Acme"
    assert body["qty"] == 400
    assert body["status"] == "PENDING_APPROVAL"


def test_approve_order():
    client.post("/orders", json=BAKERY_BIG)
    response = client.post("/orders/1/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"


def test_cannot_approve_twice():
    client.post("/orders", json=BAKERY_BIG)
    client.post("/orders/1/approve")
    response = client.post("/orders/1/approve")
    assert response.status_code == 409


def test_cannot_approve_rejected_order():
    client.post("/orders", json=BAKERY_BIG)
    client.post("/orders/1/reject")
    response = client.post("/orders/1/approve")
    assert response.status_code == 409


def test_unknown_order_returns_404():
    response = client.get("/orders/999")
    assert response.status_code == 404


def test_no_supplier_means_no_order():
    response = client.post(
        "/orders", json={"stock": 0, "incoming": 0, "daily_usage": 200}
    )
    assert response.status_code == 400
    assert ORDERS == {}

def fake_paypal_order(amount, description):
    return {
        "id": "FAKE123",
        "links": [{"rel": "payer-action", "href": "https://example.com/approve"}],
    }


def test_cannot_pay_before_approval(monkeypatch):
    monkeypatch.setattr("app.main.create_paypal_order", fake_paypal_order)
    client.post("/orders", json=BAKERY_BIG)
    response = client.post("/orders/1/pay")
    assert response.status_code == 409


def test_pay_approved_order_returns_link(monkeypatch):
    monkeypatch.setattr("app.main.create_paypal_order", fake_paypal_order)
    client.post("/orders", json=BAKERY_BIG)
    client.post("/orders/1/approve")
    response = client.post("/orders/1/pay")
    assert response.status_code == 200
    body = response.json()
    assert body["approval_url"] == "https://example.com/approve"
    assert body["order"]["status"] == "PAYMENT_STARTED"
    assert body["order"]["paypal_order_id"] == "FAKE123"

def fake_authorize(paypal_order_id):
    return {"purchase_units": [{"payments": {"authorizations": [{"id": "AUTH999"}]}}]}


def test_return_page_authorizes_order(monkeypatch):
    monkeypatch.setattr("app.main.create_paypal_order", fake_paypal_order)
    monkeypatch.setattr("app.main.authorize_paypal_order", fake_authorize)
    client.post("/orders", json=BAKERY_BIG)
    client.post("/orders/1/approve")
    client.post("/orders/1/pay")
    response = client.get(
        "/paypal/return", params={"token": "FAKE123"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/?payment=authorized&order=1")
    order = client.get("/orders/1").json()
    assert order["status"] == "AUTHORIZED"
    assert order["authorization_id"] == "AUTH999"


def test_return_page_unknown_token_is_404():
    response = client.get("/paypal/return", params={"token": "NOPE"})
    assert response.status_code == 404

def fake_capture(authorization_id):
    return {"id": "CAP777", "status": "COMPLETED"}


def make_authorized_order_via_api(monkeypatch):
    monkeypatch.setattr("app.main.create_paypal_order", fake_paypal_order)
    monkeypatch.setattr("app.main.authorize_paypal_order", fake_authorize)
    client.post("/orders", json=BAKERY_BIG)
    client.post("/orders/1/approve")
    client.post("/orders/1/pay")
    client.get("/paypal/return", params={"token": "FAKE123"}, follow_redirects=False)


def test_confirm_delivery_captures_payment(monkeypatch):
    make_authorized_order_via_api(monkeypatch)
    monkeypatch.setattr("app.main.capture_authorization", fake_capture)
    response = client.post("/orders/1/confirm-delivery")
    assert response.status_code == 200
    assert response.json()["order"]["status"] == "DELIVERED_CAPTURED"
    assert response.json()["order"]["capture_id"] == "CAP777"


def test_cannot_confirm_delivery_before_authorized(monkeypatch):
    monkeypatch.setattr("app.main.create_paypal_order", fake_paypal_order)
    monkeypatch.setattr("app.main.capture_authorization", fake_capture)
    client.post("/orders", json=BAKERY_BIG)
    client.post("/orders/1/approve")
    client.post("/orders/1/pay")
    response = client.post("/orders/1/confirm-delivery")
    assert response.status_code == 409

def test_stock_unchanged_until_delivery(monkeypatch):
    make_authorized_order_via_api(monkeypatch)
    # approved, paid and authorized, but nothing delivered yet
    assert STOCK["boxes"] == 600


def test_stock_increases_on_delivery(monkeypatch):
    make_authorized_order_via_api(monkeypatch)
    monkeypatch.setattr("app.main.capture_authorization", fake_capture)
    client.post("/orders/1/confirm-delivery")
    assert STOCK["boxes"] == 1000  # 600 + 400 ordered


def test_failed_capture_does_not_change_stock(monkeypatch):
    make_authorized_order_via_api(monkeypatch)

    def broken_capture(authorization_id):
        raise RuntimeError("PayPal is down")

    monkeypatch.setattr("app.main.capture_authorization", broken_capture)
    response = client.post("/orders/1/confirm-delivery")
    assert response.status_code == 502
    assert STOCK["boxes"] == 600
    assert client.get("/orders/1").json()["status"] == "AUTHORIZED"

SAMPLE_EVENT = {
    "id": "WH-1",
    "event_type": "PAYMENT.CAPTURE.COMPLETED",
    "summary": "Payment completed",
}


def test_webhook_logs_event():
    response = client.post("/webhooks/paypal", json=SAMPLE_EVENT)
    assert response.status_code == 200
    assert response.json() == {"status": "received"}
    assert EVENTS[0]["type"] == "PAYMENT.CAPTURE.COMPLETED"


def test_duplicate_webhook_is_logged_once():
    client.post("/webhooks/paypal", json=SAMPLE_EVENT)
    response = client.post("/webhooks/paypal", json=SAMPLE_EVENT)
    assert response.json() == {"status": "duplicate"}
    assert len(EVENTS) == 1


def test_webhook_without_id_is_rejected():
    response = client.post("/webhooks/paypal", json={"event_type": "X"})
    assert response.status_code == 400
    assert EVENTS == []


def test_webhook_does_not_change_orders_or_stock():
    client.post("/orders", json=BAKERY_BIG)
    client.post("/webhooks/paypal", json=SAMPLE_EVENT)
    assert STOCK["boxes"] == 600
    assert client.get("/orders/1").json()["status"] == "PENDING_APPROVAL"

BAKERY_SMALL = {"stock": 120, "incoming": 0, "daily_usage": 40, "buffer_days": 3}


def test_recommend_includes_explanation(monkeypatch):
    monkeypatch.setattr(
        "app.main.explain_recommendation",
        lambda facts: {"text": "Order soon.", "source": "gemini"},
    )
    body = client.post("/recommend", json=BAKERY_SMALL).json()
    assert body["explanation"] == {"text": "Order soon.", "source": "gemini"}
    assert body["supplier"]["name"] == "Acme"
    assert body["qty"] == 80
    assert body["total"] == 160


def test_ai_receives_the_computed_numbers(monkeypatch):
    seen = {}

    def fake_explain(facts):
        seen.update(facts)
        return {"text": "x", "source": "gemini"}

    monkeypatch.setattr("app.main.explain_recommendation", fake_explain)
    client.post("/recommend", json=BAKERY_SMALL)
    assert seen["supplier"] == "Acme"
    assert seen["qty"] == 80
    assert seen["days_left"] == 3
    assert seen["needs_approval"] is False


def test_recommend_still_works_when_ai_is_down(monkeypatch):
    def broken_client(api_key=None):
        raise RuntimeError("down")

    monkeypatch.setattr("app.ai.genai.Client", broken_client)
    response = client.post("/recommend", json=BAKERY_SMALL)
    assert response.status_code == 200
    body = response.json()
    assert body["qty"] == 80
    assert body["explanation"]["source"] == "fallback"

@pytest.fixture(autouse=True)
def allow_webhook_signatures(monkeypatch):
    # By default, pretend PayPal says the signature is valid.
    monkeypatch.setattr("app.main.verify_webhook_signature", lambda headers, event: True)


def test_unsigned_webhook_is_rejected(monkeypatch):
    monkeypatch.setattr("app.main.verify_webhook_signature", lambda headers, event: False)
    response = client.post("/webhooks/paypal", json=SAMPLE_EVENT)
    assert response.status_code == 401
    assert EVENTS == []
    assert SEEN_EVENT_IDS == set()


def test_webhook_is_rejected_if_verification_errors(monkeypatch):
    def broken(headers, event):
        raise RuntimeError("PayPal down")

    monkeypatch.setattr("app.main.verify_webhook_signature", broken)
    response = client.post("/webhooks/paypal", json=SAMPLE_EVENT)
    assert response.status_code == 401
    assert EVENTS == []

def test_timeline_shows_stock_update_after_delivery(monkeypatch):
    make_authorized_order_via_api(monkeypatch)
    monkeypatch.setattr("app.main.capture_authorization", fake_capture)
    client.post("/orders/1/confirm-delivery")
    timeline = client.get("/orders/1").json()["timeline"]
    assert [e["type"] for e in timeline] == [
        "ORDER_CREATED",
        "APPROVED",
        "PAYMENT_STARTED",
        "AUTHORIZED",
        "DELIVERED_CAPTURED",
        "STOCK_UPDATED",
    ]

def age_authorization(days):
    old = datetime.now(timezone.utc) - timedelta(days=days)
    ORDERS[1].authorized_at = old.isoformat()


def test_expired_authorization_blocks_capture(monkeypatch):
    make_authorized_order_via_api(monkeypatch)
    age_authorization(30)

    def must_not_be_called(authorization_id):
        raise AssertionError("PayPal should not be called")

    monkeypatch.setattr("app.main.capture_authorization", must_not_be_called)
    response = client.post("/orders/1/confirm-delivery")
    assert response.status_code == 409
    assert "expired" in response.json()["detail"]
    assert STOCK["boxes"] == 600
    assert client.get("/orders/1").json()["status"] == "AUTHORIZED"


def test_old_authorization_still_tries_capture(monkeypatch):
    make_authorized_order_via_api(monkeypatch)
    age_authorization(5)
    monkeypatch.setattr("app.main.capture_authorization", fake_capture)
    response = client.post("/orders/1/confirm-delivery")
    assert response.status_code == 200
    assert STOCK["boxes"] == 1000


def test_failed_capture_on_old_authorization_warns(monkeypatch):
    make_authorized_order_via_api(monkeypatch)
    age_authorization(5)

    def broken_capture(authorization_id):
        raise RuntimeError("declined")

    monkeypatch.setattr("app.main.capture_authorization", broken_capture)
    response = client.post("/orders/1/confirm-delivery")
    assert response.status_code == 502
    assert "may have expired" in response.json()["detail"]
    assert STOCK["boxes"] == 600

@pytest.fixture(autouse=True)
def fixed_ai_choice(monkeypatch):
    # Tests never call Gemini. By default the "AI" picks Acme.
    monkeypatch.setattr(
        "app.compare.choose_supplier",
        lambda opts: {"name": "Acme", "reason": "Test choice."},
    )


def test_recommend_returns_comparison_and_choice(monkeypatch):
    monkeypatch.setattr(
        "app.main.explain_recommendation", lambda facts: {"text": "x", "source": "gemini"}
    )
    body = client.post("/recommend", json=BAKERY_SMALL).json()
    assert [o["name"] for o in body["options"]] == ["Pricey", "Acme"]
    assert [o["chosen"] for o in body["options"]] == [False, True]
    assert body["options"][0]["reliability"] == 0.98
    assert body["choice"] == {"supplier": "Acme", "reason": "Test choice.", "source": "gemini"}


def test_recommend_with_no_options_has_no_choice(monkeypatch):
    monkeypatch.setattr(
        "app.main.explain_recommendation", lambda facts: {"text": "x", "source": "gemini"}
    )
    body = client.post(
        "/recommend", json={"stock": 0, "incoming": 0, "daily_usage": 200}
    ).json()
    assert body["options"] == []
    assert body["choice"] is None
    assert body["supplier"] is None
    assert body["message"] == "No eligible supplier. Escalate to the owner."


def test_order_uses_the_chosen_supplier(monkeypatch):
    monkeypatch.setattr(
        "app.compare.choose_supplier",
        lambda opts: {"name": "Pricey", "reason": "Fastest."},
    )
    body = client.post("/orders", json=BAKERY_BIG).json()
    assert body["supplier_name"] == "Pricey"
    assert body["qty"] == 200
    assert body["total"] == 600

def test_items_lists_inventory_with_risk():
    rows = {r["item"]: r for r in client.get("/items").json()}
    assert rows["boxes"]["days_left"] == 3
    assert rows["boxes"]["risk"] == "warning"
    assert rows["flour"]["risk"] == "ok"
    assert rows["butter"]["days_left"] == 1
    assert rows["butter"]["risk"] == "critical"


def test_items_reflect_stock_after_delivery(monkeypatch):
    make_authorized_order_via_api(monkeypatch)
    monkeypatch.setattr("app.main.capture_authorization", fake_capture)
    client.post("/orders/1/confirm-delivery")
    rows = {r["item"]: r for r in client.get("/items").json()}
    assert rows["boxes"]["stock"] == 1000
    assert rows["boxes"]["risk"] == "ok"


def test_orders_list_is_empty_at_first():
    assert client.get("/orders").json() == []


def test_orders_list_shows_created_orders():
    client.post("/orders", json=BAKERY_BIG)
    orders = client.get("/orders").json()
    assert len(orders) == 1
    assert orders[0]["status"] == "PENDING_APPROVAL"


def test_cors_allows_the_dashboard_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_blocks_other_origins():
    response = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers

def test_order_for_named_supplier_does_not_ask_the_ai(monkeypatch):
    def must_not_be_called(opts):
        raise AssertionError("AI should not be called")

    monkeypatch.setattr("app.compare.choose_supplier", must_not_be_called)
    body = client.post("/orders", json={**BAKERY_BIG, "supplier": "Pricey"}).json()
    assert body["supplier_name"] == "Pricey"
    assert body["qty"] == 200
    assert body["total"] == 600


def test_order_for_ineligible_supplier_is_rejected():
    response = client.post("/orders", json={**BAKERY_BIG, "supplier": "Slowco"})
    assert response.status_code == 400
    assert ORDERS == {}


def test_order_for_unknown_supplier_is_rejected():
    response = client.post("/orders", json={**BAKERY_BIG, "supplier": "Nobody"})
    assert response.status_code == 400
    assert ORDERS == {}

def test_cancel_redirects_to_dashboard():
    response = client.get("/paypal/cancel", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/?payment=cancelled")


def test_second_return_visit_is_rejected(monkeypatch):
    monkeypatch.setattr("app.main.create_paypal_order", fake_paypal_order)
    monkeypatch.setattr("app.main.authorize_paypal_order", fake_authorize)
    client.post("/orders", json=BAKERY_BIG)
    client.post("/orders/1/approve")
    client.post("/orders/1/pay")
    client.get("/paypal/return", params={"token": "FAKE123"}, follow_redirects=False)
    response = client.get(
        "/paypal/return", params={"token": "FAKE123"}, follow_redirects=False
    )
    assert response.status_code == 409

def test_reset_clears_orders_and_restores_stock():
    client.post("/orders", json=BAKERY_BIG)
    STOCK["boxes"] = 1000
    response = client.post("/demo/reset")
    assert response.status_code == 200
    assert ORDERS == {}
    assert STOCK == {"boxes": 600, "flour": 900, "butter": 10}


def test_reset_clears_webhook_log():
    client.post("/webhooks/paypal", json=SAMPLE_EVENT)
    assert len(EVENTS) == 1
    client.post("/demo/reset")
    assert EVENTS == []
    assert SEEN_EVENT_IDS == set()


def test_reset_is_disabled_outside_demo_mode(monkeypatch):
    monkeypatch.setattr("app.main.DEMO_MODE", False)
    client.post("/orders", json=BAKERY_BIG)
    response = client.post("/demo/reset")
    assert response.status_code == 403
    assert len(ORDERS) == 1