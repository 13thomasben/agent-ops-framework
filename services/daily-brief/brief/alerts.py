"""Failure + anomaly alerts — a DM to the service owner, via the app's BOT token
(the one Slack token type that is workspace-level; it can send DMs, never read
them)."""
from __future__ import annotations

from . import config, credentials
from .pulls import slack


def dm_owner(text: str) -> None:
    try:
        token = credentials.slack_bot_token()
        target = config.ops()["alert_slack_user_id"]
        opened = slack.api(token, "conversations.open", {"users": target})
        channel = opened["channel"]["id"]
        slack.api(token, "chat.postMessage", {"channel": channel, "text": text})
    except Exception as e:  # alerting must never take the pipeline down
        print(f"[alerts] could not DM owner: {e}")


def run_failed(user_email: str, error: str) -> None:
    dm_owner(f":rotating_light: Accountability Brief run FAILED for {user_email}\n```{error[:500]}```")


def zero_items_anomaly(user_email: str, yesterday_shown: int) -> None:
    dm_owner(
        f":warning: Accountability Brief for {user_email} shows ZERO open items today "
        f"after {yesterday_shown} yesterday. Because items only leave via detected "
        f"closure, every one should have a close_reason in the items table — worth a "
        f"30-second look that they're real. The all-clear brief was still sent."
    )
