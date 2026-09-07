from datetime import date, datetime, timedelta, timezone

from brief import score
from tests.conftest import make_item

MONDAY = date(2026, 7, 27)


def _days_ago(n: int) -> datetime:
    return datetime(2026, 7, 27, 12, tzinfo=timezone.utc) - timedelta(days=n)


def test_repeat_ask_escalates_to_blocking():
    it = make_item(repeat_count=2, first_seen=_days_ago(4))
    assert score.assign_tier(it, MONDAY) == "blocking"


def test_explicit_blocking():
    it = make_item(is_blocking=True, first_seen=_days_ago(1))
    assert score.assign_tier(it, MONDAY) == "blocking"


def test_business_day_window_email_internal():
    # internal email window = 2 business days. Sent Thursday, checked Monday:
    # Fri + Mon = 2 bd → NOT overdue yet. Sent Wednesday → 3 bd → overdue.
    thu = make_item(first_seen=_days_ago(4), counterparty_class="internal")
    wed = make_item(first_seen=_days_ago(5), counterparty_class="internal")
    assert score.assign_tier(thu, MONDAY) == "aging"
    assert score.assign_tier(wed, MONDAY) == "overdue"


def test_customer_email_one_day_window():
    fri = make_item(first_seen=_days_ago(3), counterparty_class="customer")
    assert score.business_days_between(fri["first_seen"].date(), MONDAY) == 1
    assert score.assign_tier(fri, MONDAY) == "aging"       # exactly 1 bd = at window, not past
    thu = make_item(first_seen=_days_ago(4), counterparty_class="customer")
    assert score.assign_tier(thu, MONDAY) == "overdue"


def test_deadline_today_and_past():
    today_item = make_item(deadline=MONDAY, first_seen=_days_ago(1))
    past_item = make_item(deadline=MONDAY - timedelta(days=3), first_seen=_days_ago(4))
    assert score.assign_tier(today_item, MONDAY) == "today"
    assert score.assign_tier(past_item, MONDAY) == "overdue"


def test_days_open_dominates_score():
    old = make_item(first_seen=_days_ago(9), counterparty_class="vendor")
    fresh = make_item(first_seen=_days_ago(1), counterparty_class="customer")
    assert score.score_item(old, MONDAY) > score.score_item(fresh, MONDAY)


def test_select_caps_and_counts():
    items = [make_item(id=f"i{n}", block="A", first_seen=_days_ago(1), days_open=1)
             for n in range(18)]
    items += [make_item(id=f"d{n}", block="D", first_seen=_days_ago(n + 1), days_open=n + 1)
              for n in range(6)]
    sel = score.select(items, MONDAY)
    assert len(sel["shown"]) == 15          # cap across A–C
    assert sel["not_shown"] == 3
    assert len(sel["waiting"]) == 6         # D uncapped
    assert sel["counts"]["total_open"] == 18
