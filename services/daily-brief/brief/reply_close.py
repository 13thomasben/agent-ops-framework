"""Checklist item 10 — reply-to-close. The pressure valve for classifier
false positives, and a stream of labeled data on what the system got wrong.

Reads replies landing in the brief mailbox, matches "close 4, 7" (also
tolerates "close 4 7", "close 4 and 7", "Close #4"), resolves the numbers
against the sender's MOST RECENT brief (brief_items froze that numbering),
and closes with reason 'manual'. Dedupe is by internetMessageId, so the app
needs only Mail.Read."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import requests

from . import config, credentials, store
from .pulls import graph

CLOSE_RE = re.compile(r"\bclose[:\s#]*((?:#?\d+[\s,;&]*(?:and\s+)?)+)", re.IGNORECASE)


def parse_positions(body: str) -> list[int]:
    """Extract item numbers from the FIRST 'close ...' directive in the reply.
    Only text above the quoted original is considered."""
    top = re.split(r"\n\s*(?:>|From:|On .{0,80} wrote:)", body or "", maxsplit=1)[0]
    m = CLOSE_RE.search(top)
    if not m:
        return []
    return sorted({int(n) for n in re.findall(r"\d+", m.group(1))})


def _already_processed(message_id: str) -> bool:
    with store.conn() as c:
        return c.execute(
            "select 1 from reply_close_log where message_id = %s", (message_id,)
        ).fetchone() is not None


def _log(message_id: str, from_email: str, body: str, positions: list[int],
         closed: list[str], note: str) -> None:
    with store.conn() as c:
        c.execute(
            """insert into reply_close_log (message_id, from_email, body_excerpt,
                                            parsed_positions, closed_item_ids, note)
               values (%s, %s, %s, %s, %s, %s)
               on conflict (message_id) do nothing""",
            (message_id, from_email, (body or "")[:300], positions, closed, note),
        )


def run(lookback_hours: int = 48) -> dict:
    """Poll the brief mailbox and process new replies. Returns counts for the
    run log."""
    mailbox = config.ops()["brief_mailbox"]
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    roster_by_email = {p["email"].lower(): p for p in config.people()}
    counts = {"seen": 0, "processed": 0, "closed": 0, "unparsed": 0, "unknown_sender": 0}

    r = requests.get(
        f"{graph.BASE}/users/{mailbox}/mailFolders/inbox/messages",
        params={
            "$select": "id,internetMessageId,from,subject,receivedDateTime,bodyPreview",
            "$top": 50, "$orderby": "receivedDateTime desc",
            "$filter": f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        },
        headers={"Authorization": f"Bearer {credentials.m365_token()}"},
        timeout=60,
    )
    r.raise_for_status()

    for msg in r.json().get("value", []):
        counts["seen"] += 1
        mid = msg.get("internetMessageId") or msg["id"]
        if _already_processed(mid):
            continue
        counts["processed"] += 1
        sender = graph.addr(msg.get("from"))
        person = roster_by_email.get(sender)
        if not person:
            _log(mid, sender, msg.get("bodyPreview", ""), [], [], "unknown_sender")
            counts["unknown_sender"] += 1
            continue

        body = graph.get_body_text(mailbox, msg["id"]) or msg.get("bodyPreview", "")
        positions = parse_positions(body)
        if not positions:
            _log(mid, sender, body, [], [], "unparsed")
            counts["unparsed"] += 1
            continue

        brief = store.latest_brief(person["email"])
        if not brief:
            _log(mid, sender, body, positions, [], "no_brief_on_record")
            continue

        closed_ids = []
        misses = []
        for pos in positions:
            item_id = brief["positions"].get(pos)
            if item_id:
                store.close_item(item_id, "manual", f"reply-to-close #{pos} by {sender}")
                closed_ids.append(item_id)
            else:
                misses.append(pos)
        note = "ok" if not misses else f"positions_not_in_brief:{misses}"
        _log(mid, sender, body, positions, closed_ids, note)
        counts["closed"] += len(closed_ids)
    return counts
