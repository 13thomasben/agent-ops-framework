import pytest

from scout.schema import Listing, ListingState
from scout.state import InvalidTransition, ListingStore


def make_listing(lid="123"):
    return Listing(id=lid, url=f"https://facebook.com/marketplace/item/{lid}",
                   title="Solid maple dresser", price=180.0)


@pytest.fixture()
def store(tmp_path):
    s = ListingStore(tmp_path / "state.sqlite3")
    yield s
    s.close()


def test_happy_path_transitions(store):
    store.upsert(make_listing())
    for nxt in [ListingState.SCORED, ListingState.INQUIRING, ListingState.NEGOTIATING,
                ListingState.AGREED, ListingState.AWAITING_APPROVAL,
                ListingState.SCHEDULED, ListingState.DONE]:
        store.transition("123", nxt)
    assert store.state_of("123") is ListingState.DONE


def test_illegal_jump_raises(store):
    store.upsert(make_listing())
    with pytest.raises(InvalidTransition):
        store.transition("123", ListingState.AGREED)  # spotted -> agreed is nonsense


def test_dead_reachable_from_anywhere(store):
    store.upsert(make_listing())
    store.transition("123", ListingState.SCORED)
    store.transition("123", ListingState.DEAD, note="sold out from under us")
    assert store.state_of("123") is ListingState.DEAD


def test_state_survives_reopen(store, tmp_path):
    store.upsert(make_listing("77"))
    store.transition("77", ListingState.SCORED)
    reopened = ListingStore(tmp_path / "state.sqlite3")
    assert reopened.state_of("77") is ListingState.SCORED
    reopened.close()


def test_active_view_excludes_terminal(store):
    store.upsert(make_listing("a"))
    store.upsert(make_listing("b"))
    store.transition("b", ListingState.DEAD)
    ids = [row["id"] for row in store.active()]
    assert "a" in ids and "b" not in ids
