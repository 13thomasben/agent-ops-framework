from pathlib import Path

import pytest

from scout.geo import Geo
from scout.pipeline import Pipeline, apply_money_math, gates
from scout.schema import DealVerdict, Listing, TransportClass, Want
from scout.state import ListingStore
from scout.sources.upstream_cache import from_upstream_dict, parse_price


def make_listing(lid="42", price=180.0, location="Silver Spring, MD", slug="dresser"):
    return Listing(id=lid, url=f"https://fb.test/{lid}", title="Solid maple dresser",
                   price=price, location=location, want_slug=slug)


def make_verdict(**over) -> DealVerdict:
    base = dict(fit=9, quality=8, fair_value=300.0, max_price=190.0,
                opening_offer=120.0, transport_class=TransportClass.TWO_PERSON,
                notify=True, summary="great deal")
    base.update(over)
    return DealVerdict(**base)


def test_parse_price_variants():
    assert parse_price("$1,234") == 1234.0
    assert parse_price("CA$50") == 50.0
    assert parse_price("Free") == 0.0
    assert parse_price(75) == 75.0


def test_upstream_dict_mapping():
    listing = from_upstream_dict({
        "marketplace": "facebook", "name": "dresser", "id": "99",
        "title": "Dresser", "image": "https://img/x.jpg", "price": "$120",
        "post_url": "https://facebook.com/marketplace/item/99", "location": "Arlington, VA",
        "seller": "Sam", "condition": "Used - good", "description": "solid oak",
    })
    assert listing.want_slug == "dresser" and listing.price == 120.0
    assert listing.photos == ["https://img/x.jpg"]


def test_money_math_recomputed_in_code():
    v = apply_money_math(make_verdict(), make_listing(price=180.0), 8.0)
    assert v.delivery_cost == pytest.approx(96.42, abs=0.1)   # lugg 8mi
    assert v.all_in_cost == pytest.approx(276.42, abs=0.1)
    assert v.value_ratio == pytest.approx(0.921, abs=0.01)


def test_gates_value_bar():
    want = Want(slug="dresser", brief="b", value_bar=0.6)
    v = apply_money_math(make_verdict(fair_value=300.0), make_listing(price=180.0), 8.0)
    assert not gates(v, want).passed            # 0.92 > 0.6
    v2 = apply_money_math(make_verdict(fair_value=500.0), make_listing(price=180.0), 8.0)
    assert gates(v2, want).passed               # 276/500 = 0.55


def test_gates_block_scam_and_budget_and_fit():
    want = Want(slug="d", brief="b", value_bar=0.9, max_budget=250)
    v = apply_money_math(make_verdict(scam_flags=["stock photos"], fair_value=999),
                         make_listing(price=100.0), 2.0)
    assert "scam" in gates(v, want).reasons[0]
    v2 = apply_money_math(make_verdict(fair_value=999), make_listing(price=260.0), 2.0)
    assert any("budget" in r for r in gates(v2, want).reasons)
    v3 = apply_money_math(make_verdict(fit=4, fair_value=999), make_listing(price=100.0), 2.0)
    assert any("fit" in r for r in gates(v3, want).reasons)


@pytest.fixture()
def pipeline(tmp_path: Path):
    store = ListingStore(tmp_path / "s.sqlite3")
    geo = Geo(anchor="38.9072,-77.0369", cache_path=tmp_path / "g.json")
    notified: list[str] = []
    p = Pipeline(
        store=store,
        geo=geo,
        wants=[Want(slug="dresser", brief="a dresser", value_bar=0.6)],
        score_fn=lambda listing, want, **kw: make_verdict(fair_value=600.0),
        notify_fn=lambda listing, verdict, want: notified.append(listing.id),
        log=lambda msg: None,
    )
    p.notified = notified  # type: ignore[attr-defined]
    yield p
    store.close()


def test_pipeline_notifies_once_and_dedupes(pipeline: Pipeline):
    listing = make_listing()
    assert pipeline.run_once([listing]) == 1
    assert pipeline.notified == ["42"]
    assert pipeline.run_once([listing]) == 0          # same (id, price) → skipped
    assert pipeline.run_once([make_listing(price=150.0)]) == 1  # price drop re-scores


def test_pipeline_ignores_unknown_want(pipeline: Pipeline):
    assert pipeline.run_once([make_listing(slug="mystery")]) == 0
    assert pipeline.notified == []
