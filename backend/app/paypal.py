import os
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv()


def get_access_token() -> str:
    """Ask PayPal for a short-lived access token."""
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    secret = os.getenv("PAYPAL_CLIENT_SECRET")
    base_url = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")

    if not client_id or not secret:
        raise RuntimeError("PayPal credentials are missing. Check your .env file.")

    response = httpx.post(
        f"{base_url}/v1/oauth2/token",
        auth=(client_id, secret),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def create_paypal_order(amount: float, description: str) -> dict:
    """Create a PayPal order that authorizes payment without capturing it."""
    base_url = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    token = get_access_token()

    response = httpx.post(
        f"{base_url}/v2/checkout/orders",
        headers={
            "Authorization": f"Bearer {token}",
            "PayPal-Request-Id": str(uuid.uuid4()),
        },
        json={
            "intent": "AUTHORIZE",
            "purchase_units": [
                {
                    "description": description,
                    "amount": {"currency_code": "USD", "value": f"{amount:.2f}"},
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "return_url": "http://127.0.0.1:8000/paypal/return",
                        "cancel_url": "http://127.0.0.1:8000/paypal/cancel",
                        "user_action": "PAY_NOW",
                    }
                }
            },
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def authorize_paypal_order(paypal_order_id: str) -> dict:
    """After the buyer approves, reserve the money (no charge yet)."""
    base_url = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    token = get_access_token()

    response = httpx.post(
        f"{base_url}/v2/checkout/orders/{paypal_order_id}/authorize",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": f"authorize-{paypal_order_id}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def capture_authorization(authorization_id: str) -> dict:
    """Take the reserved money. Call this only after delivery is confirmed."""
    base_url = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    token = get_access_token()

    response = httpx.post(
        f"{base_url}/v2/payments/authorizations/{authorization_id}/capture",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": f"capture-{authorization_id}",
        },
        json={"final_capture": True},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


WEBHOOK_HEADERS = [
    "paypal-auth-algo",
    "paypal-cert-url",
    "paypal-transmission-id",
    "paypal-transmission-sig",
    "paypal-transmission-time",
]


def verify_webhook_signature(headers, event: dict) -> bool:
    """Ask PayPal whether this webhook event is genuine."""
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        return False
    if any(not headers.get(name) for name in WEBHOOK_HEADERS):
        return False

    base_url = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    token = get_access_token()
    response = httpx.post(
        f"{base_url}/v1/notifications/verify-webhook-signature",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": webhook_id,
            "webhook_event": event,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("verification_status") == "SUCCESS"
