from scout.approvals.telegram_bot import buttons_for, format_card
from scout.schema import DealVerdict, Listing, TransportClass, Want


def test_card_contains_math_and_escapes_html():
    listing = Listing(id="7", url="https://fb.test/7", title="Dresser <mint> & clean",
                      price=150.0, want_slug="dresser")
    verdict = DealVerdict(fit=9, quality=8, fair_value=400.0, max_price=220.0,
                          opening_offer=140.0, transport_class=TransportClass.TWO_PERSON,
                          delivery_cost=96.0, all_in_cost=246.0, value_ratio=0.615,
                          distance_miles=7.5, fit_notes="58in x 33in — inside target",
                          missing_info=["drawer video"], summary="Take it.")
    card = format_card(listing, verdict, Want(slug="dresser", brief="b"))
    assert "&lt;mint&gt;" in card and "<mint>" not in card
    assert "$246" in card and "62% of value" in card and "7.5 mi" in card
    assert "open $140" in card and "walk above $220" in card
    assert "drawer video" in card


def test_buttons_carry_listing_id():
    kb = buttons_for("abc123")
    datas = [b["callback_data"] for b in kb["inline_keyboard"][0]]
    assert datas == ["watch:abc123", "kill:abc123", "draft:abc123"]
