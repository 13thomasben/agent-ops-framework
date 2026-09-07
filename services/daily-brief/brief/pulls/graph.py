"""Microsoft Graph client + a per-user mailbox snapshot.

One snapshot per user per run serves three consumers — Block A (inbound),
Block D (outbound), and the closure detector — so each mailbox is paged
exactly once per folder per morning."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from .. import credentials

BASE = "https://graph.microsoft.com/v1.0"
_SELECT = ("id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,"
           "conversationId,bodyPreview,webLink,isDraft")


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(
        f"{BASE}{path}",
        params=params,
        headers={"Authorization": f"Bearer {credentials.m365_token()}",
                 "Prefer": 'outlook.body-content-type="text"'},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def list_messages(upn: str, folder: str, since: datetime, max_pages: int = 4) -> list[dict]:
    ts_field = "sentDateTime" if folder == "sentitems" else "receivedDateTime"
    url = f"/users/{upn}/mailFolders/{folder}/messages"
    params = {
        "$select": _SELECT,
        "$top": 50,
        "$orderby": f"{ts_field} desc",
        "$filter": f"{ts_field} ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
    }
    out: list[dict] = []
    for _ in range(max_pages):
        data = _get(url, params)
        out.extend(data.get("value", []))
        nxt = data.get("@odata.nextLink")
        if not nxt:
            break
        url, params = nxt.replace(BASE, ""), None
    return out


def get_body_text(upn: str, message_id: str) -> str:
    data = _get(f"/users/{upn}/messages/{message_id}", {"$select": "body"})
    return (data.get("body") or {}).get("content", "")


def send_mail(from_upn: str, to_email: str, subject: str, html: str) -> None:
    r = requests.post(
        f"{BASE}/users/{from_upn}/sendMail",
        json={
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": html},
                "toRecipients": [{"emailAddress": {"address": to_email}}],
                "replyTo": [{"emailAddress": {"address": from_upn}}],
            },
            "saveToSentItems": True,
        },
        headers={"Authorization": f"Bearer {credentials.m365_token()}"},
        timeout=60,
    )
    r.raise_for_status()


def addr(msg_side: dict | None) -> str:
    return ((msg_side or {}).get("emailAddress") or {}).get("address", "").lower()


def name_and_addr(msg_side: dict | None) -> str:
    ea = (msg_side or {}).get("emailAddress") or {}
    n, a = ea.get("name", ""), ea.get("address", "")
    return f"{n} <{a}>" if n else a


def is_calendar_message(msg: dict) -> bool:
    return "eventMessage" in (msg.get("@odata.type") or "")


def ts(msg: dict) -> datetime:
    raw = msg.get("receivedDateTime") or msg.get("sentDateTime")
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@dataclass
class MailboxSnapshot:
    upn: str
    lookback_days: int
    inbox: list[dict] = field(default_factory=list)
    sent: list[dict] = field(default_factory=list)

    def load(self) -> "MailboxSnapshot":
        since = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        self.inbox = [m for m in list_messages(self.upn, "inbox", since) if not m.get("isDraft")]
        self.sent = [m for m in list_messages(self.upn, "sentitems", since) if not m.get("isDraft")]
        return self

    def by_conversation(self) -> dict[str, list[dict]]:
        conv: dict[str, list[dict]] = {}
        for m in self.inbox + self.sent:
            conv.setdefault(m.get("conversationId") or m["id"], []).append(m)
        for msgs in conv.values():
            msgs.sort(key=ts)
        return conv
