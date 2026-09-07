import pytest

from scout.schema import TransportClass
from scout.transport import cost_menu, delivery_quote


def test_close_sedan_is_self_pickup():
    q = delivery_quote(TransportClass.SEDAN, 4.0)
    assert q.cost == 0.0 and q.method == "self pickup"


def test_courier_for_sedan_beyond_self_radius():
    q = delivery_quote(TransportClass.SEDAN, 12.0)
    assert q.cost == 25.0 and q.method == "courier"


def test_two_person_uses_lugg_math():
    q = delivery_quote(TransportClass.TWO_PERSON, 8.0)
    assert q.cost == pytest.approx(38 + 8 * 2.24 + 25 * 1.62)  # base + miles + labor


def test_unknown_distance_never_counts_as_close():
    q = delivery_quote(TransportClass.SEDAN, None)
    assert q.cost > 0 and q.distance_known is False


def test_cost_menu_has_all_tiers():
    menu = cost_menu(8.0)
    assert set(menu) == {"sedan", "suv", "two_person"}
    assert menu["two_person"] > menu["suv"] >= 0
