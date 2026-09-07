"""Block B — inbound Slack awaiting the user's response (spec §2, 14-day
lookback): DMs and direct @-mentions with no text reply from the user.

The user's Path B token sees exactly what the user sees — nothing more."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Candidate, counts_as_words
from . import filtering, slack


def pull(user: dict, token: str, lookback_days: int, cap: int = 30) -> list[Candidate]:
    uid = user["slack_user_id"]
    after = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    seen_threads: set[str] = set()
    out: list[Candidate] = []

    matches = (slack.search_messages(token, f"to:me after:{after}") +
               slack.search_messages(token, f"<@{uid}> after:{after}"))
    matches.sort(key=lambda m: float(m.get("ts", "0")), reverse=True)

    for m in matches:
        channel = (m.get("channel") or {}).get("id", "")
        ts = m.get("ts", "")
        if not channel or not ts or filtering.do_not_ingest_channel(channel):
            continue
        text = m.get("text", "")
        sender = m.get("user", "")
        if not sender or sender == uid:
            continue
        if filtering.is_channel_broadcast(text, uid):
            continue

        full = slack.get_message(token, channel, ts)
        if full is None or not slack.is_human_message(full):
            continue
        thread_root = full.get("thread_ts") or ts
        source_id = f"{channel}:{thread_root}"
        if source_id in seen_threads:
            continue
        seen_threads.add(source_id)

        replies = slack.thread_replies(token, channel, thread_root)
        humans = [r for r in replies if slack.is_human_message(r)]
        # NOTE (the emoji rule): the reactions array on these messages is never
        # inspected anywhere in this codebase. Only a WORDS reply from the user
        # counts as a response.
        asks = [r for r in humans if r.get("user") == sender]
        latest_ask = asks[-1] if asks else full
        if any(r.get("user") == uid and float(r["ts"]) > float(latest_ask["ts"])
               and counts_as_words(r.get("text")) for r in humans):
            continue  # user already responded with words

        tail = " | ".join(
            f"{slack.user_name(token, r.get('user',''))}: {r.get('text','')[:120]}"
            for r in humans[-3:]
        )
        out.append(Candidate(
            user_email=user["email"], block="B", source="slack", source_id=source_id,
            permalink=m.get("permalink"),
            counterparty=slack.user_name(token, sender),
            text=latest_ask.get("text", text)[:2500],
            asked_at=datetime.fromtimestamp(float(latest_ask["ts"]), tz=timezone.utc),
            thread_tail=tail,
        ))
        if len(out) >= cap:
            break
    return out
