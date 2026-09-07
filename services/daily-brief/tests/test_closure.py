"""The closure detector honors spec §3: words close, emoji never does —
even when the reactions array is sitting right there in the payload."""
from datetime import datetime, timedelta, timezone

from brief import closure, store
from brief.models import stable_id
from brief.pulls import slack as slack_mod

USER = {"email": "sponsor@acme.example.com", "key": "sponsor",
        "slack_user_id": "U_EXAMPLE_SPONSOR", "jira_account_id": None}
TWO_DAYS_AGO = datetime.now(timezone.utc) - timedelta(days=2)


def _seed_slack_item(pg) -> str:
    item_id = stable_id(USER["email"], "slack", "C777:1700.100")
    with store.conn() as c:
        c.execute(
            """insert into items (id, user_email, block, source, source_id, ask_summary,
                                  counterparty_class, first_seen, last_ask_at)
               values (%s, %s, 'B', 'slack', 'C777:1700.100', 'Share the Product Roadmap page',
                       'internal', %s, %s)""",
            (item_id, USER["email"], TWO_DAYS_AGO, TWO_DAYS_AGO),
        )
    return item_id


def _run_closure_with_thread(monkeypatch, messages):
    monkeypatch.setattr(slack_mod, "thread_replies", lambda tok, ch, ts: messages)
    return closure.run_for_user(USER, snapshot=None, slack_token="xoxp-test")


def _open_ids():
    return {i["id"] for i in store.open_items(USER["email"])}


def test_reaction_does_not_close(pg, monkeypatch):
    """The sponsor 👍-reacted (a reaction AND a shortcode reply). Item must stay
    fully open — this is the single most important rule in the spec."""
    item_id = _seed_slack_item(pg)
    now_ts = f"{datetime.now(timezone.utc).timestamp():.6f}"
    thread = [
        {"user": "U_EXAMPLE_ASKER", "ts": f"{TWO_DAYS_AGO.timestamp():.6f}",
         "text": "Where does the strategy doc live?",
         "reactions": [{"name": "thumbsup", "users": ["U_EXAMPLE_SPONSOR"], "count": 1}]},
        # even a typed emoji-shortcode "reply" is not words:
        {"user": "U_EXAMPLE_SPONSOR", "ts": now_ts, "text": ":thumbsup:"},
    ]
    counts = _run_closure_with_thread(monkeypatch, thread)
    assert item_id in _open_ids(), "reaction closed an item — spec violation"
    assert counts["reply"] == 0


def test_words_reply_closes(pg, monkeypatch):
    item_id = _seed_slack_item(pg)
    now_ts = f"{datetime.now(timezone.utc).timestamp():.6f}"
    thread = [
        {"user": "U_EXAMPLE_ASKER", "ts": f"{TWO_DAYS_AGO.timestamp():.6f}",
         "text": "Where does the strategy doc live?"},
        {"user": "U_EXAMPLE_SPONSOR", "ts": now_ts,
         "text": "Just shared the Confluence page with you"},
    ]
    counts = _run_closure_with_thread(monkeypatch, thread)
    assert item_id not in _open_ids()
    assert counts["reply"] == 1
    row = [i for i in _all_items()]
    assert row and row[0]["close_reason"] == "reply"


def _all_items():
    with store.conn() as c:
        return c.execute("select * from items").fetchall()


def test_reply_before_ask_does_not_close(pg, monkeypatch):
    """A words reply OLDER than the latest ask doesn't close it (the repeat
    ask re-opened the obligation)."""
    item_id = _seed_slack_item(pg)
    old_ts = f"{(TWO_DAYS_AGO - timedelta(days=1)).timestamp():.6f}"
    thread = [
        {"user": "U_EXAMPLE_SPONSOR", "ts": old_ts, "text": "Will send it over tomorrow"},
        {"user": "U_EXAMPLE_ASKER", "ts": f"{TWO_DAYS_AGO.timestamp():.6f}",
         "text": "Ping — still need the Product Roadmap page"},
    ]
    _run_closure_with_thread(monkeypatch, thread)
    assert item_id in _open_ids()


def test_manual_close(pg):
    item_id = _seed_slack_item(pg)
    store.close_item(item_id, "manual", "reply-to-close #2 by sponsor@acme.example.com")
    assert item_id not in _open_ids()
