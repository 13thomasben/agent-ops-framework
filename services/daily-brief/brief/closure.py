"""Checklist item 6 — the closure detector. Runs against every open item from
prior days, every morning, BEFORE the brief renders.

What closes an item (spec §3): a WORDS reply from the user · an observable
action (ticket status moved, reassigned) · someone else resolving it ·
a manual close via reply-to-close.

What does NOT close an item: any emoji reaction · marking read · viewing a
thread · time passing. The reactions array on Slack messages is not ignored
here so much as unreachable — `brief.pulls.slack` exposes no way to read it."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from . import credentials, store
from .models import counts_as_words
from .pulls import graph, slack


def run_for_user(user: dict, snapshot: graph.MailboxSnapshot | None,
                 slack_token: str | None) -> dict:
    """Sweep the user's open items; close what the sources prove closed.
    Returns counts per close reason for the run log."""
    counts = {"reply": 0, "action": 0, "third_party": 0, "source_gone": 0, "checked": 0}
    conv = snapshot.by_conversation() if snapshot else {}
    ue = user["email"].lower()

    for item in store.open_items(user["email"]):
        counts["checked"] += 1
        try:
            if item["source"] == "email" and snapshot is not None:
                _check_email(item, conv, ue, counts)
            elif item["source"] == "slack" and slack_token:
                _check_slack(item, slack_token, ue, user["slack_user_id"], counts)
            elif item["source"] == "jira":
                _check_jira(item, user, counts)
        except Exception:
            # A closure check that errors leaves the item OPEN. Failing open is
            # the safe direction: a loop lingering one extra day beats a loop
            # silently vanishing without a detected response.
            continue
    return counts


# --- email -------------------------------------------------------------------

def _check_email(item: dict, conv: dict, ue: str, counts: dict) -> None:
    conv_id = item["source_id"].removesuffix("#d")
    msgs = conv.get(conv_id)
    if not msgs:
        return  # thread older than snapshot lookback — leave open; reply-to-close is the valve

    anchor = item["last_ask_at"] or item["first_seen"]
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    after = [m for m in msgs if graph.ts(m) > anchor]

    if item["block"] == "A":
        # 1) the user replied with words
        for m in after:
            if graph.addr(m.get("from")) == ue and counts_as_words(m.get("bodyPreview")):
                store.close_item(item["id"], "reply", f"user replied {m.get('sentDateTime') or m.get('receivedDateTime')}")
                counts["reply"] += 1
                return
        # 2) someone else answered the thread with words
        asker = _addr_of(item.get("counterparty"))
        for m in after:
            sender = graph.addr(m.get("from"))
            if sender not in (ue, asker) and counts_as_words(m.get("bodyPreview")):
                store.close_item(item["id"], "third_party", f"{sender} answered")
                counts["third_party"] += 1
                return
    else:  # block D: the counterparty replied with words → loop resolved
        for m in after:
            if graph.addr(m.get("from")) != ue and counts_as_words(m.get("bodyPreview")):
                store.close_item(item["id"], "reply", f"{graph.addr(m.get('from'))} replied")
                counts["reply"] += 1
                return


def _addr_of(counterparty: str | None) -> str:
    if counterparty and "<" in counterparty:
        return counterparty.split("<")[-1].rstrip(">").strip().lower()
    return (counterparty or "").lower()


# --- slack -------------------------------------------------------------------

def _check_slack(item: dict, token: str, ue: str, uid: str, counts: dict) -> None:
    channel, _, rest = item["source_id"].partition(":")
    thread_ts = rest.removesuffix("#d")
    try:
        replies = slack.thread_replies(token, channel, thread_ts)
    except slack.SlackError as e:
        if "not_found" in str(e) or "channel_not_found" in str(e):
            store.close_item(item["id"], "source_gone", str(e))
            counts["source_gone"] += 1
        return

    anchor = item["last_ask_at"] or item["first_seen"]
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    anchor_ts = anchor.timestamp()
    humans = [r for r in replies if slack.is_human_message(r)]
    # The emoji rule, enforced by absence: `replies` carries whatever Slack
    # returns, but the ONLY fields read below are user, ts, and text. A 👍,
    # an 👀, a ✅ — none of it exists as far as this function can see.
    if item["block"] == "B":
        for r in humans:
            if r.get("user") == uid and float(r["ts"]) > anchor_ts and counts_as_words(r.get("text")):
                store.close_item(item["id"], "reply", f"user replied at ts {r['ts']}")
                counts["reply"] += 1
                return
    else:  # block D
        for r in humans:
            if r.get("user") != uid and float(r["ts"]) > anchor_ts and counts_as_words(r.get("text")):
                store.close_item(item["id"], "reply", f"<@{r.get('user')}> replied at ts {r['ts']}")
                counts["reply"] += 1
                return


# --- jira --------------------------------------------------------------------

def _check_jira(item: dict, user: dict, counts: dict) -> None:
    base = credentials.jira_base()
    r = requests.get(f"{base}/rest/api/3/issue/{item['source_id']}",
                     params={"fields": "status,assignee"},
                     auth=credentials.jira_auth(), timeout=30)
    if r.status_code == 404:
        store.close_item(item["id"], "source_gone", "issue deleted")
        counts["source_gone"] += 1
        return
    r.raise_for_status()
    f = r.json()["fields"]
    status = (f.get("status") or {}).get("name", "")
    category = ((f.get("status") or {}).get("statusCategory") or {}).get("key", "")
    assignee = ((f.get("assignee") or {}).get("accountId")) or ""
    if status.lower() in ("done", "closed", "resolved") or category == "done":
        store.close_item(item["id"], "action", f"status → {status}")
        counts["action"] += 1
    elif assignee and assignee != user.get("jira_account_id"):
        store.close_item(item["id"], "third_party", f"reassigned to {assignee}")
        counts["third_party"] += 1
