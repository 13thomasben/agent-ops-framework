"""Hash stability (the persistence anchor) and the emoji rule's words test."""
from brief.models import counts_as_words, stable_id


def test_stable_id_is_stable():
    a = stable_id("sponsor@acme.example.com", "slack", "C123:1721.001")
    b = stable_id("Sponsor@acme.example.com ", "slack", "C123:1721.001")  # case/space noise
    assert a == b
    assert len(a) == 16


def test_stable_id_differs_by_any_component():
    base = stable_id("u@acme.example.com", "slack", "C1:1")
    assert stable_id("v@acme.example.com", "slack", "C1:1") != base
    assert stable_id("u@acme.example.com", "email", "C1:1") != base
    assert stable_id("u@acme.example.com", "slack", "C1:2") != base


def test_emoji_is_not_words():
    # THE rule: reactions and emoji-only replies leave an item fully open.
    assert not counts_as_words("👍")
    assert not counts_as_words("👀👀")
    assert not counts_as_words("✅")
    assert not counts_as_words(":thumbsup:")
    assert not counts_as_words("")
    assert not counts_as_words(None)
    assert not counts_as_words("!!")
    assert not counts_as_words("+1")


def test_words_are_words():
    assert counts_as_words("ok will do")
    assert counts_as_words("Routing through procurement first, then legal.")


def test_short_but_real_replies():
    # "no" alone is 2 letters — below the 5-letter floor, treated as not enough.
    # "No, route via legal" passes. This is the conservative reading: a
    # borderline non-answer keeps the loop open, and reply-to-close exists.
    assert not counts_as_words("no")
    assert counts_as_words("no, route via legal")
