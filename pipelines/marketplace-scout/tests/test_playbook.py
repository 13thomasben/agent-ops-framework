from scout.negotiation.playbook import Action, build_plan, decide
from scout.schema import DealVerdict


def verdict(fair=220.0, max_price=190.0, opening=125.0) -> DealVerdict:
    return DealVerdict(
        fit=9, quality=8, fair_value=fair, max_price=max_price,
        opening_offer=opening, summary="test",
    )


def test_plan_shape():
    plan = build_plan(verdict(), asking_price=180)
    assert plan.ceiling == 180                      # min(190, 180)
    assert plan.opening == 125                      # round5(0.7 * 180)
    assert plan.offers[0] == plan.opening
    assert plan.offers[-1] == plan.ceiling
    assert list(plan.offers) == sorted(set(plan.offers))  # strictly ascending
    assert plan.opening <= plan.target <= plan.ceiling


def test_never_offers_above_ask_or_ceiling():
    plan = build_plan(verdict(max_price=500.0), asking_price=180)
    assert plan.ceiling == 180
    assert all(o <= 180 for o in plan.offers)


def test_accepts_at_or_below_target():
    plan = build_plan(verdict(), asking_price=180)
    d = decide(plan.target, plan, offers_made=1)
    assert d.action is Action.ACCEPT


def test_counters_stay_inside_ceiling():
    plan = build_plan(verdict(), asking_price=180)
    d = decide(plan.ceiling - 5, plan, offers_made=1)
    if d.action is Action.COUNTER:
        assert d.amount is not None and d.amount <= plan.ceiling


def test_walks_when_seller_stays_above_ceiling_and_ladder_exhausted():
    plan = build_plan(verdict(), asking_price=180)
    d = decide(250, plan, offers_made=len(plan.offers))
    assert d.action is Action.WALK


def test_unparseable_price_escalates():
    plan = build_plan(verdict(), asking_price=180)
    assert decide(0, plan, offers_made=0).action is Action.ESCALATE
