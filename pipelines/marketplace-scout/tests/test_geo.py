from pathlib import Path

import pytest

from scout.geo import DC_CENTER, GAZETTEER, Geo, haversine_miles


@pytest.fixture()
def geo(tmp_path: Path) -> Geo:
    # anchor = downtown DC via explicit coords; isolated cache file
    return Geo(anchor="38.9072,-77.0369", cache_path=tmp_path / "cache.json")


def test_haversine_sanity():
    assert haversine_miles(DC_CENTER, GAZETTEER["baltimore"]) == pytest.approx(35, abs=4)


def test_gazetteer_substring_match(geo: Geo):
    assert geo.miles_from_home("Silver Spring, MD") == pytest.approx(5.8, abs=1.5)
    assert geo.miles_from_home("Arlington, VA") == pytest.approx(3.2, abs=1.5)


def test_far_places_are_far(geo: Geo):
    assert geo.miles_from_home("Baltimore, MD") > 25
    assert geo.miles_from_home("Fredericksburg, VA") > 35


def test_unknown_location_returns_none(tmp_path: Path):
    geo = Geo(anchor="38.9,-77.03", cache_path=tmp_path / "c.json")
    geo._nominatim = lambda text: None  # no network in tests
    assert geo.miles_from_home("Some Nowhere Township, ZZ") is None


def test_anchor_default_flag(tmp_path: Path):
    geo = Geo(anchor="", cache_path=tmp_path / "c.json")
    assert geo.anchor_default is True
    geo2 = Geo(anchor="petworth", cache_path=tmp_path / "c2.json")
    assert geo2.anchor_default is False
