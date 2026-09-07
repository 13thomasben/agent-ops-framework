import pytest

from scout.closing.lugg import estimate


def test_dresser_move_math_matches_published_rates():
    est = estimate(miles=8, labor_minutes=20)
    assert est.total == pytest.approx(38 + 8 * 2.24 + 20 * 1.62)  # 88.32


def test_estimate_rejects_negatives():
    with pytest.raises(ValueError):
        estimate(miles=-1)


def test_pretty_is_card_friendly():
    assert "Lugg Pickup" in estimate(5).pretty
