from app.compare import evaluate_suppliers
from app.decision import decision_record, top_action
from app.inventory import Item
from app.policy import Policy
from app.suppliers import Supplier

POLICY = Policy(max_auto_spend=150, budget=1500)


def butter() -> Item:
    return Item("Butter", "Dairy", "kg", stock=12, daily_usage=12, incoming=0, unit_cost=6.5, criticality=3)


def suppliers() -> list[Supplier]:
    return [
        Supplier("FreshMart", 6.8, 1, min_order_qty=10, delivery_fee=15, reliability=0.92, history_count=12),
        Supplier("BakersChoice", 6.3, 2, min_order_qty=20, delivery_fee=20, reliability=None, history_count=2),
        Supplier("Shady Traders", 3.0, 1, approved=False),
    ]


def evaluate():
    item = butter()
    options, rejected = evaluate_suppliers(item.stock, item.incoming, item.daily_usage, suppliers(), POLICY, 3)
    return item, options, rejected


def record(**overrides):
    item, options, rejected = evaluate()
    args = dict(
        item=item, options=options, rejected=rejected, chosen=options[0], policy=POLICY,
        buffer_days=3, budget_remaining=422.1, chosen_by="fallback", days_left=1.0,
    )
    args.update(overrides)
    return decision_record(**args)


def test_record_lists_who_was_considered_and_who_was_rejected():
    rec = record()
    assert [c["name"] for c in rec["considered"]] == ["FreshMart"]
    assert rec["considered"][0]["chosen"] is True
    rejected = {r["name"]: r["reasons"] for r in rec["rejected"]}
    assert set(rejected) == {"BakersChoice", "Shady Traders"}
    assert "Not on the approved supplier list" in rejected["Shady Traders"]
    assert "stock runs out" in rejected["BakersChoice"][0]


def test_record_copies_the_chosen_numbers_from_the_option():
    item, options, rejected = evaluate()
    rec = record()
    chosen = options[0]
    assert rec["chosen"]["supplier"] == "FreshMart"
    assert rec["chosen"]["qty"] == chosen.qty
    assert rec["chosen"]["total"] == chosen.total
    assert rec["chosen"]["delivery_fee"] == 15
    assert rec["budget_remaining_before"] == 422.1


def test_record_states_the_rules_and_assumptions_with_real_limits():
    rec = record()
    text = " ".join(rec["rules"])
    assert "$1,500.00" in text and "$150.00" in text
    assert "1.0 days of stock left" in text
    assumptions = " ".join(rec["assumptions"])
    assert "12 kg a day" in assumptions
    assert "3-day buffer" in assumptions


def test_rule_about_arrival_is_left_out_when_there_is_no_usage():
    rec = record(days_left=None)
    assert not any("runs out" in r for r in rec["rules"])


def test_unknown_reliability_is_mentioned_only_when_it_applies():
    item = butter()
    only_known = [s for s in suppliers() if s.name == "FreshMart"]
    options, rejected = evaluate_suppliers(item.stock, item.incoming, item.daily_usage, only_known, POLICY, 3)
    rec = decision_record(
        item=item, options=options, rejected=rejected, chosen=options[0], policy=POLICY,
        buffer_days=3, budget_remaining=None, chosen_by="rules", days_left=1.0,
    )
    assert not any("fewer than 3" in a for a in rec["assumptions"])
    assert rec["budget_remaining_before"] is None


def test_default_reasons_by_who_chose():
    assert "only one" in record(chosen_by="rules")["reason"].lower()
    assert "Decision Lab" in record(chosen_by="decision_lab")["reason"]
    assert "lowest total cost" in record(chosen_by="fallback")["reason"]
    assert "You chose FreshMart" in record(chosen_by="owner")["reason"]


def test_usage_note_replaces_the_average_on_record_wording():
    plain = " ".join(record()["assumptions"])
    assert "12 kg a day, the average on record." in plain
    stressed = " ".join(record(usage_note="the average on record +50% for the stress test")["assumptions"])
    assert "12 kg a day, the average on record +50% for the stress test." in stressed


def test_a_given_reason_is_kept_as_written():
    assert record(chosen_by="gemini", reason="Fastest and reliable.")["reason"] == "Fastest and reliable."


def test_owner_reason_reports_the_extra_cost_over_the_cheapest():
    item = Item("Flour", "Dry goods", "kg", stock=120, daily_usage=40, incoming=0, unit_cost=0.9, criticality=3)
    offers = [
        Supplier("FreshMart", 0.95, 1, min_order_qty=200, delivery_fee=15),
        Supplier("BakersChoice", 0.88, 2, min_order_qty=100, delivery_fee=20),
    ]
    options, rejected = evaluate_suppliers(item.stock, item.incoming, item.daily_usage, offers, POLICY, 3)
    by_name = {o.supplier.name: o for o in options}
    pricier = max(options, key=lambda o: o.total)
    cheaper = min(options, key=lambda o: o.total)
    rec = decision_record(
        item=item, options=options, rejected=rejected, chosen=pricier, policy=POLICY,
        buffer_days=3, budget_remaining=100.0, chosen_by="owner", days_left=3.0,
    )
    extra = round(pricier.total - cheaper.total, 2)
    assert f"${extra:,.2f} more than {cheaper.supplier.name}" in rec["reason"]
    assert set(by_name) == {"FreshMart", "BakersChoice"}


def test_top_action_picks_the_cheapest_supplier_that_arrives_in_time():
    item, options, _ = evaluate()
    action = top_action(item=item, options=options, days_left=1.0, budget_remaining=422.1)
    assert action["item"] == "Butter"
    assert action["supplier"] == "FreshMart"
    assert action["total"] == options[0].total
    assert action["lead_time_days"] == 1
    assert action["fits_budget"] is True


def test_top_action_says_when_it_does_not_fit_the_budget():
    item, options, _ = evaluate()
    action = top_action(item=item, options=options, days_left=1.0, budget_remaining=50.0)
    assert action["fits_budget"] is False
    assert action["budget_remaining"] == 50.0


def test_top_action_is_none_without_a_usable_supplier():
    assert top_action(item=butter(), options=[], days_left=1.0, budget_remaining=100.0) is None
