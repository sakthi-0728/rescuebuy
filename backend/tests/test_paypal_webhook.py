from app.paypal import WEBHOOK_HEADERS, verify_webhook_signature

HEADERS = {name: f"value-{name}" for name in WEBHOOK_HEADERS}
EVENT = {"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}


class FakeResponse:
    def __init__(self, status):
        self._status = status

    def raise_for_status(self):
        pass

    def json(self):
        return {"verification_status": self._status}


def setup_paypal(monkeypatch, status="SUCCESS"):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        return FakeResponse(status)

    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WEBHOOK-ID-1")
    monkeypatch.setattr("app.paypal.get_access_token", lambda: "token")
    monkeypatch.setattr("app.paypal.httpx.post", fake_post)
    return sent


def test_success_is_accepted(monkeypatch):
    setup_paypal(monkeypatch, "SUCCESS")
    assert verify_webhook_signature(HEADERS, EVENT) is True


def test_failure_is_rejected(monkeypatch):
    setup_paypal(monkeypatch, "FAILURE")
    assert verify_webhook_signature(HEADERS, EVENT) is False


def test_missing_webhook_id_is_rejected(monkeypatch):
    setup_paypal(monkeypatch)
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID")
    assert verify_webhook_signature(HEADERS, EVENT) is False


def test_missing_headers_are_rejected(monkeypatch):
    sent = setup_paypal(monkeypatch)
    assert verify_webhook_signature({}, EVENT) is False
    assert sent == {}  # PayPal was never called


def test_sends_event_and_webhook_id_to_paypal(monkeypatch):
    sent = setup_paypal(monkeypatch)
    verify_webhook_signature(HEADERS, EVENT)
    assert sent["url"].endswith("/v1/notifications/verify-webhook-signature")
    assert sent["json"]["webhook_id"] == "WEBHOOK-ID-1"
    assert sent["json"]["webhook_event"] == EVENT