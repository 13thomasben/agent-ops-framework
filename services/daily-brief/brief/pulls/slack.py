"""Slack client running AS THE USER (Path B user token).

Deliberate omission, per the single most important rule in the spec: this
module has no function that reads reactions. Not filtered out — never fetched.
An emoji cannot close an item if the pipeline is incapable of seeing it."""
from __future__ import annotations

import time
from functools import lru_cache

import requests


class SlackError(RuntimeError):
    pass


def api(token: str, method: str, params: dict | None = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        r = requests.post(
            f"https://slack.com/api/{method}",
            data=params or {},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "3")) + 1)
            continue
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            if data.get("error") == "ratelimited" and attempt < retries - 1:
                time.sleep(3)
                continue
            raise SlackError(f"{method}: {data.get('error')}")
        return data
    raise SlackError(f"{method}: rate-limited after {retries} attempts")


def search_messages(token: str, query: str, max_results: int = 60) -> list[dict]:
    out: list[dict] = []
    page = 1
    while len(out) < max_results:
        data = api(token, "search.messages",
                   {"query": query, "count": 50, "page": page, "sort": "timestamp"})
        matches = (data.get("messages") or {}).get("matches", [])
        out.extend(matches)
        paging = (data.get("messages") or {}).get("paging", {})
        if page >= int(paging.get("pages", 1)):
            break
        page += 1
    return out[:max_results]


def get_message(token: str, channel: str, ts: str) -> dict | None:
    """Fetch one message (search matches don't carry thread_ts reliably)."""
    data = api(token, "conversations.history",
               {"channel": channel, "latest": ts, "inclusive": "true", "limit": 1})
    msgs = data.get("messages", [])
    return msgs[0] if msgs and msgs[0].get("ts") == ts else None


def thread_replies(token: str, channel: str, thread_ts: str) -> list[dict]:
    data = api(token, "conversations.replies",
               {"channel": channel, "ts": thread_ts, "limit": 100})
    return data.get("messages", [])


@lru_cache(maxsize=512)
def user_name(token: str, slack_id: str) -> str:
    try:
        info = api(token, "users.info", {"user": slack_id})
        prof = info["user"]
        return prof.get("real_name") or prof.get("name") or slack_id
    except SlackError:
        return slack_id


@lru_cache(maxsize=512)
def im_partner(token: str, channel: str) -> str | None:
    """For a DM channel, the other participant's user ID."""
    try:
        info = api(token, "conversations.info", {"channel": channel})
        return (info.get("channel") or {}).get("user")
    except SlackError:
        return None


def is_human_message(m: dict) -> bool:
    return bool(m.get("user")) and not m.get("bot_id") and m.get("subtype") in (None, "thread_broadcast")
