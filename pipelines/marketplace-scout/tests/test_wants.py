from pathlib import Path

from scout.schema import Want
from scout.wants import load_wants, save_want, slugify, upstream_item_section


def test_save_and_load_roundtrip(tmp_path: Path):
    want = Want(slug="reading_lamp", brief="A mid-century floor lamp.\nBrass 'ok'.",
                search_phrases=["floor lamp", "mid century lamp"], max_budget=120)
    save_want(want, tmp_path)
    loaded = load_wants(tmp_path)
    assert len(loaded) == 1
    got = loaded[0]
    assert got.slug == "reading_lamp"
    assert got.max_budget == 120
    assert "mid-century" in got.brief
    assert got.search_phrases == ["floor lamp", "mid century lamp"]


def test_inactive_wants_are_skipped(tmp_path: Path):
    save_want(Want(slug="dead", brief="x", active=False), tmp_path)
    assert load_wants(tmp_path) == []


def test_missing_dir_is_empty():
    assert load_wants(Path("/nonexistent-anywhere")) == []


def test_slugify():
    assert slugify("A 60in Wood Dresser!!") == "a_60in_wood_dresser"


def test_upstream_section_matches_slug():
    want = Want(slug="dresser", brief="b", search_phrases=["dresser"])
    section = upstream_item_section(want, 40, 400, ["wardrobe"])
    assert section.startswith("[item.dresser]")
    assert "min_price = 40" in section and "'wardrobe'" in section
