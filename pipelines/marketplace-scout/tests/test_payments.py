import pytest

from scout.payments import PaymentLinkError, cashapp_pay_link, venmo_pay_link


def test_venmo_link_prefills_everything():
    link = venmo_pay_link("@Jane-Doe-7", 160, "Maple dresser")
    assert link == "https://venmo.com/Jane-Doe-7?txn=pay&amount=160&note=Maple%20dresser"


def test_venmo_amount_keeps_cents_but_strips_zeroes():
    assert "amount=87.5&" in venmo_pay_link("seller_1", 87.50, "deposit")
    assert "amount=87.25&" in venmo_pay_link("seller_1", 87.25, "deposit")


def test_venmo_rejects_suspicious_usernames():
    with pytest.raises(PaymentLinkError):
        venmo_pay_link("j!", 50, "x")
    with pytest.raises(PaymentLinkError):
        venmo_pay_link("has space", 50, "x")


def test_amount_sanity_bounds():
    with pytest.raises(PaymentLinkError):
        venmo_pay_link("ok_user", 0, "x")
    with pytest.raises(PaymentLinkError):
        venmo_pay_link("ok_user", 2500, "x")


def test_note_is_flattened_and_capped():
    link = venmo_pay_link("ok_user", 20, "line1\nline2  " + "y" * 300)
    assert "%0A" not in link  # no newlines survive
    assert len(link) < 300


def test_cashapp_link():
    assert cashapp_pay_link("$owner", 45) == "https://cash.app/$owner/45"
    with pytest.raises(PaymentLinkError):
        cashapp_pay_link("$9bad", 45)
