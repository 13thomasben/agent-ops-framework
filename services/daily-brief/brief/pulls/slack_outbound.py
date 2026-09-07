"""Block D (Slack half) — messages the user sent containing an ask that nobody
answered with words (spec §2, 21-day lookback)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Candidate, counts_as_words
from . import filtering, slack


def pull(user: dict, token: str, lookback_days: int, cap: int = 30) -> list[Candidate]:
    uid = user["slack_user_id"]
    after = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    seen_threads: set[str] = set()
    out: list[Candidate] = []

    for m in slack.search_messages(token, f"from:me after:{after}", max_results=80):
        channel = (m.get("channel") or {}).get("id", "")
        ts = m.get("ts", "")
        if not channel or not ts or filtering.do_not_ingest_channel(channel):
            continue
        text = m.get("text", "")
        if not counts_as_words(text):
            continue

        full = slack.get_message(token, channel, ts)
        if full is None:
            continue
        thread_root = full.get("thread_ts") or ts
        source_id = f"{channel}:{thread_root}#d"
        if source_id in seen_threads:
            continue
        seen_threads.add(source_id)

        replies = slack.thread_replies(token, channel, thread_root)
        humans = [r for r in replies if slack.is_human_message(r)]
        user_msgs = [r for r in humans if r.get("user") == uid]
        last_user = user_msgs[-1] if user_msgs else full
        # Reactions are invisible here by design: an 👀 on your ask is not an answer.
        if any(r.get("user") != uid and float(r["ts"]) > float(last_user["ts"])
               and counts_as_words(r.get("text")) for r in humans):
            continue  # somebody answered with words — not an open loop

        partner = slack.im_partner(token, channel)
        counterparty = slack.user_name(token, partner) if partner else \
            f"#{(m.get('channel') or {}).get('name', channel)}"
        out.append(Candidate(
            user_email=user["email"], block="D", source="slack", source_id=source_id,
            permalink=m.get("permalink"),
            counterparty=counterparty,
            text=last_user.get("text", text)[:2500],
            asked_at=datetime.fromtimestamp(float(last_user["ts"]), tz=timezone.utc),
        ))
        if len(out) >= cap:
            break
    return out
