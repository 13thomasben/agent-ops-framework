from datetime import datetime
from zoneinfo import ZoneInfo

from scout.guardrails import Guardrails, require_human_for_money

ET = ZoneInfo("America/New_York")
DAYTIME = datetime(2026, 7, 22, 10, 30, tzinfo=ET)
MIDNIGHT = datetime(2026, 7, 22, 23, 45, tzinfo=ET)


def test_money_always_needs_human_is_not_a_setting():
    assert require_human_for_money() is True


def test_offer_ceiling_is_min_of_verdict_and_global():
    g = Guardrails()
    ok, _ = g.allow_offer(150, verdict_max_price=180)
    assert ok
    denied, why = g.allow_offer(200, verdict_max_price=180)
    assert not denied and "ceiling" in why


def test_global_cap_binds_even_with_generous_verdict():
    g = Guardrails(max_item_price=300)
    denied, _ = g.allow_offer(350, verdict_max_price=400)
    assert not denied


def test_active_hours():
    g = Guardrails()
    assert g.within_active_hours(DAYTIME)
    assert not g.within_active_hours(MIDNIGHT)


def test_send_pacing_and_thread_cap():
    g = Guardrails()
    ok, _ = g.allow_send(120, messages_in_thread=3, now=DAYTIME)
    assert ok
    too_fast, why = g.allow_send(10, messages_in_thread=3, now=DAYTIME)
    assert not too_fast and "pacing" in why
    capped, why = g.allow_send(120, messages_in_thread=30, now=DAYTIME)
    assert not capped and "thread cap" in why
    night, why = g.allow_send(120, messages_in_thread=3, now=MIDNIGHT)
    assert not night and "hours" in why


def test_daily_conversation_cap():
    g = Guardrails()
    ok, _ = g.allow_new_conversation(2)
    assert ok
    denied, _ = g.allow_new_conversation(5)
    assert not denied
