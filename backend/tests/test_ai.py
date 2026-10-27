from app.ai import choose_supplier, explain_recommendation, fallback_text

FACTS = {
    "item": "boxes",
    "days_left": 3,
    "supplier": "Acme",
    "qty": 80,
    "total": 160,
    "needs_approval": False,
}


class FakeResponse:
    def __init__(self, text):
        self.text = text


def make_fake_client(text=None, error=None):
    class FakeClient:
        def __init__(self, api_key=None):
            self.models = self

        def generate_content(self, model, contents):
            if error:
                raise error
            return FakeResponse(text)

    return FakeClient


def test_fallback_text_with_supplier():
    text = fallback_text(FACTS)
    assert "80 boxes" in text
    assert "Acme" in text
    assert "$160.00" in text


def test_fallback_text_mentions_approval():
    text = fallback_text({**FACTS, "needs_approval": True})
    assert "owner must approve" in text


def test_fallback_text_without_supplier():
    text = fallback_text({"supplier": None})
    assert text == "No eligible supplier. Escalate to the owner."


def test_uses_gemini_when_it_works(monkeypatch):
    monkeypatch.setattr("app.ai.genai.Client", make_fake_client(text="Order 80 boxes."))
    result = explain_recommendation(FACTS)
    assert result == {"text": "Order 80 boxes.", "source": "gemini"}


def test_falls_back_when_gemini_fails(monkeypatch):
    monkeypatch.setattr(
        "app.ai.genai.Client", make_fake_client(error=RuntimeError("rate limit"))
    )
    result = explain_recommendation(FACTS)
    assert result["source"] == "fallback"
    assert "Acme" in result["text"]


def test_falls_back_on_empty_response(monkeypatch):
    monkeypatch.setattr("app.ai.genai.Client", make_fake_client(text="   "))
    result = explain_recommendation(FACTS)
    assert result["source"] == "fallback"

def test_fallback_text_when_no_order_needed():
    text = fallback_text({**FACTS, "qty": 0})
    assert text == "Stock is sufficient. No order needed."

OPTIONS = [{"name": "Acme", "total": 160}, {"name": "Pricey", "total": 120}]


def test_choose_supplier_reads_json(monkeypatch):
    reply = '{"name": "Acme", "reason": "Reliable."}'
    monkeypatch.setattr("app.ai.genai.Client", make_fake_client(text=reply))
    assert choose_supplier(OPTIONS) == {"name": "Acme", "reason": "Reliable."}


def test_choose_supplier_handles_code_fences(monkeypatch):
    reply = '```json\n{"name": "Acme", "reason": "Reliable."}\n```'
    monkeypatch.setattr("app.ai.genai.Client", make_fake_client(text=reply))
    assert choose_supplier(OPTIONS) == {"name": "Acme", "reason": "Reliable."}


def test_choose_supplier_returns_none_on_bad_json(monkeypatch):
    monkeypatch.setattr("app.ai.genai.Client", make_fake_client(text="not json"))
    assert choose_supplier(OPTIONS) is None


def test_choose_supplier_returns_none_when_reason_missing(monkeypatch):
    monkeypatch.setattr(
        "app.ai.genai.Client", make_fake_client(text='{"name": "Acme"}')
    )
    assert choose_supplier(OPTIONS) is None


def test_choose_supplier_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(
        "app.ai.genai.Client", make_fake_client(error=RuntimeError("down"))
    )
    assert choose_supplier(OPTIONS) is None