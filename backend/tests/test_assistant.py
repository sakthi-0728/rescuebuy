import pytest

from app import assistant, db
from app.assistant import (
    Intent,
    ToolResult,
    ai_text_is_safe,
    answer_question,
    find_days,
    find_items,
    keyword_route,
    numbers_in,
    validate_route,
)
from app.snapshot import load_snapshot


@pytest.fixture(autouse=True)
def seeded_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RESCUEBUY_DB", str(tmp_path / "test.db"))
    db.init_db(force=True)


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    """By default the AI is unavailable, so every test exercises the fallbacks."""
    monkeypatch.setattr("app.assistant.route_question", lambda q, tools, items: None)
    monkeypatch.setattr("app.assistant.explain_answer", lambda q, a, f: None)


@pytest.fixture
def snap():
    with db.connect() as conn:
        return load_snapshot(conn)


def ask(question, snap):
    return answer_question(question, snap)


def text(question, snap):
    return ask(question, snap)["answer"]["text"]


# ---- Finding items and days in a question ----

ITEMS = ["Bakery boxes", "Flour", "Butter", "Eggs", "Paper bags", "Cocoa powder"]


def test_items_are_found_by_any_word_and_either_plural():
    assert find_items("How many boxes do I have?", ITEMS) == ["Bakery boxes"]
    assert find_items("is there a box left", ITEMS) == ["Bakery boxes"]
    assert find_items("how many egg trays", ITEMS) == ["Eggs"]
    assert find_items("paper bag stock", ITEMS) == ["Paper bags"]
    assert find_items("cocoa?", ITEMS) == ["Cocoa powder"]


def test_no_item_means_no_match():
    assert find_items("how is the weather", ITEMS) == []


def test_overlapping_item_names_are_ambiguous():
    names = ["Brown sugar", "White sugar"]
    assert find_items("how much sugar", names) == names
    assert find_items("how much brown sugar", names) == ["Brown sugar"]


def test_days_can_be_digits_or_words():
    assert find_days("run out within three days") == 3
    assert find_days("delivers 2 days late") == 2
    assert find_days("two more days") == 2
    assert find_days("what is my stock") is None


# ---- Reading the question without AI ----

@pytest.mark.parametrize(
    "question, tool, item",
    [
        ("How many boxes do I have?", "stock_of", "Bakery boxes"),
        ("How long will the flour last?", "days_left", "Flour"),
        ("How many days will the remaining flour last?", "days_left", "Flour"),
        ("How many days until I run out of butter?", "days_left", "Butter"),
        ("Which items could run out within three days?", "running_out", None),
        ("What should I reorder today?", "what_to_reorder", None),
        ("What should I reorder this week?", "what_to_reorder", None),
        ("How much will the recommended order cost?", "order_cost", None),
        ("Which supplier offers the best eligible option?", "best_supplier", None),
        ("Who is the cheapest supplier for flour?", "best_supplier", "Flour"),
        ("Am I likely to exceed my purchasing budget?", "budget_check", None),
        ("Can I afford to restock everything?", "budget_check", None),
        ("What happens if a supplier delivers two days late?", "late_supplier", None),
        ("Does anything expire soon?", "expiring", None),
        ("What is the status of my orders?", "order_status", None),
        ("butter", "stock_of", "Butter"),
    ],
)
def test_keyword_router_understands_the_example_questions(question, tool, item, snap):
    intent = keyword_route(question, snap)
    assert (intent.tool, intent.item) == (tool, item)


def test_router_reads_the_number_of_days(snap):
    assert keyword_route("what if a supplier is two days late", snap).days == 2
    assert keyword_route("which items run out within 5 days", snap).days == 5


def test_unrecognised_question_routes_to_none(snap):
    assert keyword_route("what is the capital of France", snap).tool == "none"


# ---- Checking what the AI chose ----

def test_ai_choice_is_accepted_when_the_tool_and_item_are_real(snap):
    intent = validate_route({"tool": "days_left", "item": "flour", "days": None}, snap)
    assert intent == Intent("days_left", item="Flour", days=None)


def test_ai_choice_is_rejected_for_an_unknown_tool(snap):
    assert validate_route({"tool": "delete_everything", "item": None, "days": None}, snap) is None
    assert validate_route(None, snap) is None


def test_ai_invented_item_is_dropped(snap):
    intent = validate_route({"tool": "stock_of", "item": "Unicorn dust", "days": None}, snap)
    assert intent.item is None  # the tool will then ask which item is meant


def test_ai_days_outside_a_sensible_range_are_ignored(snap):
    assert validate_route({"tool": "late_supplier", "item": None, "days": 500}, snap).days is None
    assert validate_route({"tool": "late_supplier", "item": None, "days": -2}, snap).days is None


# ---- The tools: every number is checked against the seeded data ----

def test_stock_of(snap):
    r = ask("How many boxes do I have?", snap)
    assert r["tool"] == "stock_of"
    assert "600 boxes" in r["answer"]["text"] and "3 days" in r["answer"]["text"]
    assert r["data"]["stock"] == 600
    assert any("Usage: 200 boxes a day" in b for b in r["basis"])
    assert r["answer"]["source"] == "calculated"


def test_days_left_mentions_delivery_time_and_expiry(snap):
    flour = text("How long will the flour last?", snap)
    assert "about 3 days" in flour and "120 kg at 40 kg a day" in flour and "delivers in 1 day" in flour
    eggs = text("How long will the eggs last?", snap)
    assert "about 60 trays may go unused" in eggs  # expires in 6 days, lasts 12


def test_days_left_with_no_usage_says_it_cannot_estimate(snap):
    snap.views[1]["days_left"] = None
    assert "no usage on record" in text("How long will the flour last?", snap)


def test_running_out_lists_items_soonest_first(snap):
    answer = text("Which items could run out within three days?", snap)
    assert answer.startswith("Within 3 days: Butter (1 day)")
    for name in ("Bakery boxes", "Flour", "Yeast", "Paper bags"):
        assert name in answer
    assert "Eggs" not in answer and "Sugar" not in answer


def test_running_out_with_a_shorter_window(snap):
    answer = text("Which items run out within 1 day?", snap)
    assert "Butter" in answer and "Flour" not in answer


def test_running_out_with_nothing_at_risk(snap):
    assert text("which items run out within 0 days", snap).startswith("No item is expected to run out")


def test_expiring_only_reports_items_with_expiry_data(snap):
    answer = text("Does anything expire soon?", snap)
    assert "Eggs" in answer and "60 trays may go unused" in answer
    assert "Flour" not in answer


def test_what_to_reorder_lists_items_suppliers_and_totals(snap):
    r = ask("What should I reorder today?", snap)
    assert r["tool"] == "what_to_reorder"
    assert "Butter: 36 kg from FreshMart ($259.80)" in r["answer"]["text"]
    assert "Together that is $590.80" in r["answer"]["text"]
    assert "I cannot place orders" in r["answer"]["text"]
    assert r["data"]["total"] == 590.8
    assert len(r["data"]["items"]) == 5


def test_order_cost_compares_with_the_remaining_budget(snap):
    r = ask("How much will the recommended order cost?", snap)
    assert "$590.80 across 5 items" in r["answer"]["text"]
    assert "$422.10 left" in r["answer"]["text"]


def test_budget_check_says_what_cannot_be_afforded(snap):
    answer = text("Can I afford to restock everything?", snap)
    assert "$2,277.90 of your $2,700.00" in answer
    assert "cannot afford all of it" in answer and "$168.70 over" in answer


def test_budget_check_when_everything_fits(snap):
    snap.settings["monthly_budget"] = 5000
    answer = text("Am I likely to exceed my budget?", snap)
    assert "which fits" in answer and "$2,131.30" in answer   # 5000 - 2277.90 - 590.80


def test_best_supplier_for_one_item_explains_rejections(snap):
    answer = text("Who is the cheapest supplier for flour?", snap)
    assert "BakersChoice has the lowest total: 100 kg for $108.00" in answer
    assert "FreshMart ($205.00" in answer
    assert "Budget Bulk (Delivers in 5 days" in answer


def test_best_supplier_for_an_item_that_needs_no_reorder(snap):
    assert "does not need a reorder" in text("best supplier for sugar", snap)


def test_best_supplier_without_an_item_covers_everything_that_needs_a_reorder(snap):
    answer = text("Which supplier offers the best eligible option?", snap)
    assert "Butter: FreshMart ($259.80)" in answer and "Flour: BakersChoice ($108.00)" in answer


def test_late_supplier_shows_who_would_run_out(snap):
    r = ask("What happens if a supplier delivers two days late?", snap)
    answer = r["answer"]["text"]
    assert "2 days late" in answer
    assert "fastest suppliers: Butter (2 days without stock)" in answer
    assert "Flour (1 day without stock)" in answer     # the slower, cheaper supplier
    assert r["data"]["delay_days"] == 2


def test_late_supplier_defaults_to_two_days(snap):
    assert "2 days late" in text("what if a supplier is late", snap)


def test_order_status_with_and_without_orders(snap):
    assert text("What is the status of my orders?", snap) == "You have no orders yet."
    with db.connect() as conn:
        db.create_order(conn, "Flour", "FreshMart", 200, 205.0)
        snap = load_snapshot(conn)
    assert "Order 1: Flour from FreshMart, $205.00, awaiting your approval." in text("status of my orders", snap)


# ---- Missing data and unclear questions ----

def test_a_question_without_an_item_asks_which_one(snap):
    r = ask("How many do I have?", snap)
    assert r["needs_clarification"] is True
    assert "Which item do you mean?" in r["answer"]["text"]
    assert "What is my stock of Flour?" in r["suggestions"]
    assert len(r["suggestions"]) == 8


def test_how_long_without_an_item_asks_which_one(snap):
    r = ask("How long will it last?", snap)
    assert r["needs_clarification"] is True


def test_an_item_the_business_does_not_track_is_not_invented(snap):
    r = ask("How many chocolate bars do I have?", snap)
    assert r["needs_clarification"] is True
    assert "600" not in r["answer"]["text"]


def test_unknown_questions_get_help_not_a_guess(snap):
    r = ask("what is the capital of France", snap)
    assert r["tool"] == "none"
    assert "I can answer questions about your stock" in r["answer"]["text"]
    assert r["suggestions"]


# ---- It can never act ----

@pytest.mark.parametrize(
    "question",
    ["Order 500 boxes for me", "buy more flour", "Please pay for order 1", "approve the order", "Reorder everything now",
     "place an order for butter", "Restock the butter"],
)
def test_purchase_requests_are_refused(question, snap):
    r = ask(question, snap)
    assert r["tool"] == "refuse_action"
    assert r["routed_by"] == "rules"
    assert "I cannot place, approve or pay for orders" in r["answer"]["text"]


def test_purchase_requests_never_reach_the_ai(snap, monkeypatch):
    def must_not_be_called(*args, **kwargs):
        raise AssertionError("the AI must not see purchase requests")

    monkeypatch.setattr("app.assistant.route_question", must_not_be_called)
    monkeypatch.setattr("app.assistant.explain_answer", must_not_be_called)
    assert ask("buy more flour", snap)["tool"] == "refuse_action"


def test_questions_about_orders_are_not_mistaken_for_purchases(snap):
    assert ask("order status", snap)["tool"] == "order_status"
    assert ask("What should I order this week?", snap)["tool"] == "what_to_reorder"


def test_asking_never_changes_anything(snap):
    for q in assistant.EXAMPLES:
        ask(q, snap)
    with db.connect() as conn:
        assert db.list_orders(conn) == []
        assert db.get_item(conn, "Flour").stock == 120


# ---- The number guard ----

def result(text="Order 100 kg for $108.00.", **facts):
    return ToolResult(text, facts or {"qty": 100, "total": 108.0, "days_left": 3.0}, ["Usage: 40 kg a day"])


def test_numbers_are_read_with_commas_dollars_dates_and_spelled_words():
    assert numbers_in("$2,277.90 left") == [2277.9]
    assert numbers_in("restocked 2026-10-29") == [2026.0, 10.0, 29.0]
    assert numbers_in("in two days and 3 items") == [3.0, 2.0]
    assert numbers_in("one of them") == []


def test_text_using_only_known_numbers_is_accepted():
    assert ai_text_is_safe("You need 100 kg for $108.00 and it lasts 3 days.", "q", result()) is True


def test_a_number_that_is_not_in_the_facts_is_rejected():
    assert ai_text_is_safe("You need 120 kg for $108.00.", "q", result()) is False
    assert ai_text_is_safe("That costs $108.00 and saves you $50.", "q", result()) is False


def test_a_spelled_out_invented_number_is_rejected():
    assert ai_text_is_safe("This will last about five days.", "q", result()) is False
    assert ai_text_is_safe("This will last about three days.", "q", result()) is True


def test_numbers_from_the_question_and_basis_are_allowed():
    r = result()
    assert ai_text_is_safe("At 40 kg a day.", "q", r) is True
    assert ai_text_is_safe("Over 7 days.", "what about 7 days", r) is True


def test_rounding_in_the_facts_is_tolerated():
    r = result(**{"days_left": 2.96})
    assert ai_text_is_safe("About 3 days left.", "q", r) is True


def test_claims_of_having_acted_are_rejected():
    for claim in ("I've placed the order.", "I ordered 100 kg.", "We have paid for it.", "I approved it."):
        assert ai_text_is_safe(claim, "q", result()) is False


def test_empty_or_rambling_text_is_rejected():
    assert ai_text_is_safe("", "q", result()) is False
    assert ai_text_is_safe("word " * 200, "q", result()) is False


# ---- Putting the AI in the loop ----

def test_the_ai_choice_is_used_when_valid(snap, monkeypatch):
    monkeypatch.setattr(
        "app.assistant.route_question",
        lambda q, tools, items: {"tool": "days_left", "item": "Flour", "days": None},
    )
    r = ask("hmm, will my flour hold out?", snap)   # the keyword router would not understand this
    assert r["routed_by"] == "gemini"
    assert r["tool"] == "days_left"
    assert "about 3 days" in r["answer"]["text"]


def test_a_bad_ai_choice_falls_back_to_the_keywords(snap, monkeypatch):
    monkeypatch.setattr(
        "app.assistant.route_question", lambda q, tools, items: {"tool": "explode", "item": None, "days": None}
    )
    r = ask("How many boxes do I have?", snap)
    assert r["routed_by"] == "keywords"
    assert r["tool"] == "stock_of"


def test_ai_saying_none_falls_back_to_the_keywords(snap, monkeypatch):
    monkeypatch.setattr(
        "app.assistant.route_question", lambda q, tools, items: {"tool": "none", "item": None, "days": None}
    )
    assert ask("How many boxes do I have?", snap)["routed_by"] == "keywords"


def test_an_ai_answer_with_only_known_numbers_is_shown(snap, monkeypatch):
    monkeypatch.setattr(
        "app.assistant.explain_answer",
        lambda q, a, f: "Restocking everything costs $590.80, but you only have $422.10 left.",
    )
    r = ask("Can I afford to restock everything?", snap)
    assert r["answer"]["source"] == "gemini"
    assert r["answer"]["text"].startswith("Restocking everything costs $590.80")


def test_an_ai_answer_with_an_invented_number_is_replaced(snap, monkeypatch):
    monkeypatch.setattr(
        "app.assistant.explain_answer", lambda q, a, f: "You will save $75.00 if you restock everything."
    )
    r = ask("Can I afford to restock everything?", snap)
    assert r["answer"]["source"] == "calculated"
    assert "$75.00" not in r["answer"]["text"]
    assert "$168.70 over" in r["answer"]["text"]


def test_an_ai_answer_claiming_to_have_ordered_is_replaced(snap, monkeypatch):
    monkeypatch.setattr("app.assistant.explain_answer", lambda q, a, f: "I've ordered the butter for you.")
    r = ask("What should I reorder today?", snap)
    assert r["answer"]["source"] == "calculated"


def test_simple_lookups_do_not_spend_an_ai_call_on_wording(snap, monkeypatch):
    def must_not_be_called(*args, **kwargs):
        raise AssertionError("no wording call for a simple lookup")

    monkeypatch.setattr("app.assistant.explain_answer", must_not_be_called)
    assert ask("How many boxes do I have?", snap)["answer"]["source"] == "calculated"
    assert ask("How long will the flour last?", snap)["answer"]["source"] == "calculated"


def test_clarifications_are_not_reworded(snap, monkeypatch):
    def must_not_be_called(*args, **kwargs):
        raise AssertionError("clarifications stay as they are")

    monkeypatch.setattr("app.assistant.explain_answer", must_not_be_called)
    assert ask("How many do I have?", snap)["needs_clarification"] is True


def test_every_answer_says_when_it_was_calculated(snap):
    assert ask("How many boxes do I have?", snap)["as_of"].endswith("+00:00")
