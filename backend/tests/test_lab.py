from app.compare import Option
from app.lab import (
    Candidate,
    build_candidates,
    cheapest,
    comparison_savings,
    fastest,
    make_deferred,
    make_line,
    recommended_key,
    simulate,
)
from app.inventory import Item
from app.policy import Policy, PolicyResult
from app.suppliers import Supplier

OK = PolicyResult(True, False, [])


def option(name, qty, total, lead):
    return Option(Supplier(name, unit_price=1, lead_time_days=lead), qty, total, OK)


def candidate(item, days, risk, crit, options, usage=10):
    return Candidate(item, "kg", days, usage, crit, risk, options)


def results_by_key(results):
    return {r.key: r for r in results}


# ---- Choosing an option ----

def test_cheapest_uses_the_total_and_breaks_ties_on_speed():
    c = candidate("A", 5, "warning", 2, [option("Slow", 10, 50, 3), option("Fast", 10, 50, 1), option("Dear", 10, 80, 1)])
    assert cheapest(c).supplier.name == "Fast"


def test_fastest_uses_lead_time_and_breaks_ties_on_cost():
    c = candidate("A", 5, "warning", 2, [option("Cheap", 10, 40, 3), option("Fast", 10, 90, 1), option("FastCheap", 10, 70, 1)])
    assert fastest(c).supplier.name == "FastCheap"


# ---- Lines and deferrals ----

def test_line_with_margin_has_no_stockout():
    c = candidate("A", 5, "warning", 2, [option("S", 10, 50, 2)])
    line = make_line(c, c.options[0], delay_days=0)
    assert line.arrives_in_days == 2
    assert line.margin_days == 3
    assert line.stockout_days == 0


def test_delay_can_push_the_arrival_past_the_stockout():
    c = candidate("A", 3, "warning", 2, [option("S", 10, 50, 2)])
    line = make_line(c, c.options[0], delay_days=2)
    assert line.margin_days == -1
    assert line.stockout_days == 1


def test_item_with_no_usage_never_has_a_stockout():
    c = candidate("A", None, "ok", 1, [option("S", 10, 50, 9)])
    line = make_line(c, c.options[0], delay_days=5)
    assert line.margin_days is None
    assert line.stockout_days == 0
    assert make_deferred(c, wait_days=9, delay_days=5).can_wait is True


def test_deferral_is_safe_when_it_still_arrives_in_time():
    c = candidate("A", 6, "warning", 2, [option("S", 10, 50, 2)])
    d = make_deferred(c, wait_days=3, delay_days=0)
    assert d.can_wait is True
    assert d.margin_days == 1          # 6 days of stock, arrives on day 5
    assert d.order_within_days == 4    # could wait up to 4 days


def test_deferral_uses_the_fastest_supplier():
    c = candidate("A", 4, "warning", 2, [option("Cheap", 10, 40, 4), option("Fast", 10, 90, 1)])
    d = make_deferred(c, wait_days=2, delay_days=0)
    assert d.can_wait is True          # fastest arrives on day 3, the cheap one would not


def test_deferral_that_is_too_late_reports_the_gap():
    c = candidate("A", 3, "warning", 2, [option("S", 10, 50, 2)])
    d = make_deferred(c, wait_days=2, delay_days=0)
    assert d.can_wait is False
    assert d.stockout_days == 1
    assert d.order_within_days == 1


# ---- Scenarios ----

def two_items():
    urgent = candidate("Urgent", 3, "critical", 3, [option("Fast", 10, 80, 1), option("Slow", 12, 60, 3)])
    later = candidate("Later", 6, "warning", 2, [option("Fast", 10, 50, 1), option("Slow", 10, 30, 2)])
    return [urgent, later]


def test_cheapest_and_fastest_strategies_pick_different_options():
    r = results_by_key(simulate(two_items(), budget=1000))
    assert [(l.item, l.supplier) for l in r["all_cheapest"].bought] == [("Urgent", "Slow"), ("Later", "Slow")]
    assert [(l.item, l.supplier) for l in r["all_fastest"].bought] == [("Urgent", "Fast"), ("Later", "Fast")]
    assert r["all_cheapest"].spend == 90
    assert r["all_fastest"].spend == 130


def test_a_supplier_delay_hurts_the_slow_option_first():
    r = results_by_key(simulate(two_items(), budget=1000, delay_days=1))
    # Urgent has 3 days of stock: the slow supplier (3 days) now arrives on day 4, the fast one on day 2
    assert [e["item"] for e in r["all_cheapest"].exposed] == ["Urgent"]
    assert r["all_fastest"].exposed == []


def test_without_delay_every_eligible_option_arrives_in_time():
    r = results_by_key(simulate(two_items(), budget=1000))
    assert all(x.exposed == [] for x in r.values())


def test_savings_are_measured_against_the_fastest_everything_baseline():
    r = results_by_key(simulate(two_items(), budget=1000))
    assert r["all_fastest"].savings_vs_baseline == 0
    assert r["all_cheapest"].savings_vs_baseline == 40


def test_over_budget_is_flagged_and_not_hidden():
    r = results_by_key(simulate(two_items(), budget=100))
    assert r["all_fastest"].over_budget is True
    assert r["all_fastest"].budget_remaining == -30
    assert r["all_cheapest"].over_budget is False


def test_critical_only_defers_everything_else():
    r = results_by_key(simulate(two_items(), budget=1000))["critical_only"]
    assert [l.item for l in r.bought] == ["Urgent"]
    assert [d.item for d in r.deferred] == ["Later"]


def test_fit_budget_spends_on_the_most_urgent_first():
    items = [
        candidate("Critical", 1, "critical", 3, [option("S", 10, 80, 1)]),
        candidate("Medium", 3, "warning", 2, [option("S", 10, 60, 1)]),
        candidate("Small", 3, "warning", 1, [option("S", 10, 15, 1)]),
    ]
    r = results_by_key(simulate(items, budget=100))["fit_budget"]
    assert [l.item for l in r.bought] == ["Critical", "Small"]   # Medium ($60) no longer fits
    assert [d.item for d in r.deferred] == ["Medium"]
    assert r.spend == 95
    assert r.over_budget is False


def test_fit_budget_accepts_an_exact_fit():
    items = [candidate("A", 1, "critical", 3, [option("S", 10, 100, 1)])]
    r = results_by_key(simulate(items, budget=100))["fit_budget"]
    assert [l.item for l in r.bought] == ["A"]
    assert r.budget_remaining == 0


def test_longer_waiting_creates_exposure_for_deferred_items():
    quick = results_by_key(simulate(two_items(), budget=1000, wait_days=1))["critical_only"]
    slow = results_by_key(simulate(two_items(), budget=1000, wait_days=6))["critical_only"]
    assert quick.exposed == []
    assert [e["item"] for e in slow.exposed] == ["Later"]


def test_nothing_to_buy_gives_empty_but_valid_scenarios():
    results = simulate([], budget=500)
    assert len(results) == 4
    assert all(r.spend == 0 and r.bought == [] and r.exposed == [] for r in results)
    assert all(r.budget_remaining == 500 for r in results)


# ---- The recommendation ----

def test_recommendation_prefers_within_budget_then_fewer_exposed_then_cheaper():
    r = simulate(two_items(), budget=1000)
    # fastest has no exposure but costs 130, cheapest has one exposed item
    assert recommended_key(r) in ("all_fastest", "critical_only", "fit_budget")
    chosen = results_by_key(r)[recommended_key(r)]
    assert chosen.exposed == []
    assert chosen.over_budget is False
    cheaper_safe = [x for x in r if not x.exposed and not x.over_budget]
    assert chosen.spend == min(x.spend for x in cheaper_safe)


def test_recommendation_avoids_going_over_budget():
    r = simulate(two_items(), budget=100)
    chosen = results_by_key(r)[recommended_key(r)]
    assert chosen.over_budget is False


def test_recommendation_with_nothing_to_buy_is_still_defined():
    assert recommended_key(simulate([], budget=100)) == "all_cheapest"


# ---- Building candidates ----

POLICY = Policy(max_auto_spend=500, budget=2000)


def item(name, stock, usage):
    return Item(name, "Dry goods", "kg", stock, usage, 0, 1.0, 2)


def test_only_items_that_need_a_reorder_become_candidates():
    items = [item("Low", 40, 40), item("Plenty", 5000, 10)]
    offers = {n: [Supplier("S", unit_price=1, lead_time_days=1)] for n in ("Low", "Plenty")}
    candidates, unfillable = build_candidates(items, offers, POLICY, buffer_days=3)
    assert [c.item for c in candidates] == ["Low"]
    assert unfillable == []


def test_at_risk_items_nobody_can_supply_are_reported():
    items = [item("Orphan", 40, 40), item("Late", 40, 40)]
    offers = {"Late": [Supplier("Slow", unit_price=1, lead_time_days=9)]}
    candidates, unfillable = build_candidates(items, offers, POLICY, buffer_days=3)
    assert candidates == []
    assert unfillable == ["Orphan", "Late"]


def test_candidates_are_ordered_by_urgency():
    items = [item("B", 80, 40), item("A", 40, 40), Item("C", "x", "kg", 80, 40, 0, 1.0, 3)]
    offers = {n: [Supplier("S", unit_price=1, lead_time_days=1)] for n in ("A", "B", "C")}
    candidates, _ = build_candidates(items, offers, POLICY, buffer_days=3)
    assert [c.item for c in candidates] == ["A", "C", "B"]  # A is critical, C matters more than B


# ---- Savings from comparing suppliers ----

def test_savings_use_cost_per_unit_on_the_same_quantity():
    c = candidate("A", 3, "warning", 2, [option("Pricey", 50, 100, 1), option("Value", 100, 150, 2)])
    s = comparison_savings([c])
    assert s["total"] == 50                 # 1.5/unit vs 2.0/unit, over 100 units
    assert s["items"][0]["best_supplier"] == "Value"
    assert s["items"][0]["baseline_supplier"] == "Pricey"
    assert s["items"][0]["baseline_total"] == 200


def test_no_saving_when_there_is_only_one_option_or_equal_prices():
    one = candidate("A", 3, "warning", 2, [option("S", 10, 50, 1)])
    tie = candidate("B", 3, "warning", 2, [option("X", 10, 50, 1), option("Y", 10, 50, 2)])
    s = comparison_savings([one, tie])
    assert s["items"] == []
    assert s["total"] == 0
