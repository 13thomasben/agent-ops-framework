"""Pre-classifier filters: do-not-ingest boundaries first, then noise.
Everything here is cheap string work that keeps junk away from the classifier
(and privacy-walled content away from any LLM call at all)."""
from __future__ import annotations

import re

from .. import config


def _f() -> dict:
    return config.filters()


def do_not_ingest_email(sender: str) -> bool:
    sender = (sender or "").lower()
    return any(x.lower() in sender for x in _f()["do_not_ingest"].get("email_senders", []))


def do_not_ingest_channel(channel_id: str) -> bool:
    return channel_id in set(_f()["do_not_ingest"].get("slack_channels", []))


def do_not_ingest_jira(project_key: str, labels: list[str]) -> bool:
    dni = _f()["do_not_ingest"]
    return project_key in set(dni.get("jira_projects", [])) or bool(
        set(labels or []) & set(dni.get("jira_labels", []))
    )


def is_noise_email(sender: str, subject: str) -> bool:
    n = _f()["noise"]["email"]
    sender, subject = (sender or "").lower(), subject or ""
    if any(re.search(p, sender) for p in n.get("sender_patterns", [])):
        return True
    if any(sender.endswith("@" + d) or ("." + d) in sender for d in n.get("automated_sender_domains", [])):
        return True
    return any(re.search(p, subject) for p in n.get("subject_patterns", []))


def personally_addressed(user_email: str, to_recipients: list[str]) -> bool:
    """Spec block A: 'addressed to you personally'. The user's own address must
    appear in To — CC-only and group-alias-only mail is excluded (anyone could
    answer)."""
    ue = user_email.lower()
    return any(ue == (r or "").lower() for r in to_recipients)


_BROADCAST = re.compile(r"<!(channel|here|everyone)>")


def is_channel_broadcast(text: str, user_slack_id: str) -> bool:
    """@channel/@here asks are excluded unless the user is ALSO directly
    mentioned (spec block B)."""
    if not _f()["noise"]["slack"].get("drop_channel_broadcasts", True):
        return False
    return bool(_BROADCAST.search(text or "")) and f"<@{user_slack_id}>" not in (text or "")
