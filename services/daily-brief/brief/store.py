"""All Postgres access. The store is the product: pulls and classifiers only
ever PROPOSE; this module decides what persists. Nothing here deletes an item
row, ever — closure is a timestamp, not a removal."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from .models import Candidate, Classification, stable_id


def _url() -> str:
    return os.environ["DATABASE_URL"]


@contextmanager
def conn():
    with psycopg.connect(_url(), row_factory=dict_row) as c:
        yield c
        c.commit()


def sync_roster(people: list[dict]) -> None:
    with conn() as c:
        for p in people:
            c.execute(
                """insert into users (email, key, full_name, slack_user_id, jira_account_id,
                                      mail_platform, timezone, active)
                   values (%(email)s, %(key)s, %(full_name)s, %(slack_user_id)s,
                           %(jira_account_id)s, %(mail_platform)s, %(timezone)s, %(active)s)
                   on conflict (email) do update set
                     key=excluded.key, full_name=excluded.full_name,
                     slack_user_id=excluded.slack_user_id, jira_account_id=excluded.jira_account_id,
                     mail_platform=excluded.mail_platform, timezone=excluded.timezone,
                     active=excluded.active, updated_at=now()""",
                {k: p.get(k) for k in ("email", "key", "full_name", "slack_user_id",
                                       "jira_account_id", "mail_platform", "timezone", "active")},
            )


def upsert_item(cand: Candidate, cls: Classification | None, stale_flag: bool = False) -> str:
    """Insert a new open loop or refresh an existing one. On an existing row:
    first_seen NEVER changes; a newer ask on the same thread bumps repeat_count;
    is_blocking can only escalate (never silently de-escalate)."""
    item_id = cand.id
    asked = cand.asked_at or datetime.now(timezone.utc)
    row = {
        "id": item_id,
        "user_email": cand.user_email,
        "block": cand.block,
        "source": cand.source,
        "source_id": cand.source_id,
        "permalink": cand.permalink,
        "ask_summary": (cls.ask_summary if cls else cand.text)[:300],
        "counterparty": cand.counterparty,
        "counterparty_class": cls.counterparty_class if cls else "unknown",
        "is_blocking": cls.is_blocking if cls else False,
        "deadline": cls.deadline if cls else None,
        "confidence": cls.confidence if cls else None,
        "last_ask_at": asked,
        "stale_flag": stale_flag,
    }
    with conn() as c:
        c.execute(
            """insert into items (id, user_email, block, source, source_id, permalink,
                                  ask_summary, counterparty, counterparty_class, is_blocking,
                                  deadline, confidence, last_ask_at, stale_flag)
               values (%(id)s, %(user_email)s, %(block)s, %(source)s, %(source_id)s, %(permalink)s,
                       %(ask_summary)s, %(counterparty)s, %(counterparty_class)s, %(is_blocking)s,
                       %(deadline)s, %(confidence)s, %(last_ask_at)s, %(stale_flag)s)
               on conflict (user_email, source, source_id) do update set
                 last_seen     = now(),
                 permalink     = coalesce(excluded.permalink, items.permalink),
                 ask_summary   = excluded.ask_summary,
                 counterparty  = coalesce(excluded.counterparty, items.counterparty),
                 counterparty_class = case when excluded.counterparty_class = 'unknown'
                                           then items.counterparty_class
                                           else excluded.counterparty_class end,
                 is_blocking   = items.is_blocking or excluded.is_blocking,
                 deadline      = coalesce(excluded.deadline, items.deadline),
                 confidence    = coalesce(excluded.confidence, items.confidence),
                 stale_flag    = excluded.stale_flag,
                 repeat_count  = case when excluded.last_ask_at > coalesce(items.last_ask_at, items.first_seen)
                                      then items.repeat_count + 1 else items.repeat_count end,
                 last_ask_at   = greatest(coalesce(items.last_ask_at, items.first_seen), excluded.last_ask_at),
                 -- an item that closed and then got a NEWER ask reopens as a fresh loop
                 closed_at     = case when items.closed_at is not null
                                       and excluded.last_ask_at > items.closed_at
                                      then null else items.closed_at end,
                 close_reason  = case when items.closed_at is not null
                                       and excluded.last_ask_at > items.closed_at
                                      then null else items.close_reason end,
                 first_seen    = case when items.closed_at is not null
                                       and excluded.last_ask_at > items.closed_at
                                      then now() else items.first_seen end""",
            row,
        )
    return item_id


def open_items(user_email: str) -> list[dict]:
    with conn() as c:
        return c.execute(
            "select * from open_items where user_email = %s order by first_seen",
            (user_email,),
        ).fetchall()


def close_item(item_id: str, reason: str, evidence: str = "") -> None:
    with conn() as c:
        c.execute(
            """update items set closed_at = now(), close_reason = %s, close_evidence = %s
               where id = %s and closed_at is null""",
            (reason, evidence[:500], item_id),
        )


def update_scores(scored: list[dict]) -> None:
    with conn() as c:
        for s in scored:
            c.execute("update items set tier=%s, score=%s where id=%s",
                      (s["tier"], s["score"], s["id"]))


def record_brief(user_email: str, subject: str, shown_ids: list[str],
                 not_shown: int, waiting: int, html: str) -> int:
    with conn() as c:
        brief_id = c.execute(
            """insert into briefs (user_email, subject, shown, not_shown, waiting, html)
               values (%s, %s, %s, %s, %s, %s) returning id""",
            (user_email, subject, len(shown_ids), not_shown, waiting, html),
        ).fetchone()["id"]
        for pos, item_id in enumerate(shown_ids, start=1):
            c.execute("insert into brief_items (brief_id, position, item_id) values (%s, %s, %s)",
                      (brief_id, pos, item_id))
    return brief_id


def latest_brief(user_email: str) -> dict | None:
    with conn() as c:
        b = c.execute(
            "select * from briefs where user_email=%s order by sent_at desc limit 1",
            (user_email,),
        ).fetchone()
        if not b:
            return None
        b["positions"] = {
            r["position"]: r["item_id"]
            for r in c.execute("select position, item_id from brief_items where brief_id=%s",
                               (b["id"],)).fetchall()
        }
        return b


def start_run(kind: str, user_email: str | None) -> int:
    with conn() as c:
        return c.execute(
            "insert into runs (kind, user_email) values (%s, %s) returning id",
            (kind, user_email),
        ).fetchone()["id"]


def finish_run(run_id: int, status: str, counts: dict, error: str = "") -> None:
    with conn() as c:
        c.execute(
            "update runs set finished_at=now(), status=%s, counts=%s, error=%s where id=%s",
            (status, json.dumps(counts), error[:2000] or None, run_id),
        )


def log_reply_close(from_email: str, body_excerpt: str, positions: list[int],
                    closed_ids: list[str], note: str) -> None:
    with conn() as c:
        c.execute(
            """insert into reply_close_log (from_email, body_excerpt, parsed_positions,
                                            closed_item_ids, note)
               values (%s, %s, %s, %s, %s)""",
            (from_email, body_excerpt[:300], positions, closed_ids, note),
        )


# --- credentials (Slack Path B user tokens) ---------------------------------

def save_credential(source: str, user_email: str, access_token: str,
                    refresh_token: str | None = None, scopes: str = "") -> None:
    with conn() as c:
        c.execute(
            """insert into credentials (source, user_email, access_token, refresh_token, scopes)
               values (%s, %s, %s, %s, %s)
               on conflict (source, user_email) do update set
                 access_token=excluded.access_token,
                 refresh_token=excluded.refresh_token,
                 scopes=excluded.scopes, updated_at=now()""",
            (source, user_email, access_token, refresh_token, scopes),
        )


def get_credential(source: str, user_email: str = "") -> dict | None:
    with conn() as c:
        return c.execute(
            "select * from credentials where source=%s and user_email=%s",
            (source, user_email),
        ).fetchone()
