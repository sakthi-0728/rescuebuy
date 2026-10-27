import json
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()


def fallback_text(facts: dict) -> str:
    """Plain sentence built from the numbers, used if the AI is unavailable."""
    if not facts.get("supplier"):
        return "No eligible supplier. Escalate to the owner."
    if facts.get("qty") == 0:
        return "Stock is sufficient. No order needed."
    text = (
        f"Order {facts['qty']} {facts['item']} from {facts['supplier']} "
        f"for ${facts['total']:.2f}. Stock lasts about {facts['days_left']} days."
    )
    if facts.get("needs_approval"):
        text += " The owner must approve this order."
    return text


def explain_recommendation(facts: dict) -> dict:
    """Ask Gemini to explain the numbers. Never changes them."""
    prompt = (
        "You are an assistant for a small business owner. Explain this reorder "
        "recommendation in 2 short, friendly sentences. Use ONLY the numbers "
        "given. Do not change, add, or invent any numbers.\n\n"
        f"Facts: {facts}"
    )
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Empty response")
        return {"text": text, "source": "gemini"}
    except Exception as e:
        print("AI unavailable, using fallback:", type(e).__name__)
        return {"text": fallback_text(facts), "source": "fallback"}


def choose_supplier(options: list[dict]) -> dict | None:
    """Ask Gemini to pick one option. Returns {"name", "reason"} or None on any problem."""
    prompt = (
        "You help a small business pick ONE supplier for a reorder. Every option "
        "below already passed the business rules. Weigh total cost, delivery "
        "speed, reliability, and whether the owner must approve. Reply with JSON "
        "only, no other text, in exactly this shape: "
        '{"name": "<a supplier name from the list>", '
        '"reason": "<2 short sentences using only the given numbers>"}\n\n'
        f"Options: {options}"
    )
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        data = json.loads(text)
        name, reason = data.get("name"), data.get("reason")
        if not isinstance(name, str) or not isinstance(reason, str):
            raise ValueError("Missing name or reason")
        return {"name": name, "reason": reason.strip()}
    except Exception as e:
        print("AI choice unavailable:", type(e).__name__)
        return None