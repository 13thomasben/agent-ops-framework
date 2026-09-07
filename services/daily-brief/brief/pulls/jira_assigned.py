"""Block C — open Jira PROJ issues assigned to the user (spec §2, all open).

No ask classifier here: an assigned open ticket is an open loop by definition.
Tickets with no movement in 7+ days get the stale flag the spec calls out."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from .. import config, credentials
from ..models import Candidate, Classification
from . import filtering

DONE_CATEGORY = "done"


def pull(user: dict, cap: int = 50) -> list[tuple[Candidate, Classification, bool]]:
    account_id = user.get("jira_account_id")
    if not account_id or account_id == "TBD":
        raise RuntimeError(f"jira_account_id missing for {user['email']} — RUNBOOK step 6")

    base = credentials.jira_base()
    projects = ", ".join(config.roster().get("jira_projects", ["PROJ"]))
    stale_days = config.weights()["brief"]["jira_stale_days"]
    jql = (f'assignee = "{account_id}" AND project in ({projects}) '
           f'AND statusCategory != Done ORDER BY updated ASC')

    r = requests.get(
        f"{base}/rest/api/3/search",
        params={"jql": jql, "maxResults": cap,
                "fields": "summary,status,updated,created,duedate,priority,labels,project"},
        auth=credentials.jira_auth(), timeout=60,
    )
    r.raise_for_status()

    out = []
    now = datetime.now(timezone.utc)
    for issue in r.json().get("issues", []):
        f = issue["fields"]
        key = issue["key"]
        if filtering.do_not_ingest_jira(f["project"]["key"], f.get("labels", [])):
            continue
        status = (f.get("status") or {}).get("name", "?")
        if status.lower() in ("done", "closed", "resolved"):
            continue
        updated = datetime.fromisoformat(f["updated"].replace("+0000", "+00:00"))
        stale = (now - updated).days >= stale_days
        summary = f.get("summary", "")
        cand = Candidate(
            user_email=user["email"], block="C", source="jira", source_id=key,
            permalink=f"{base}/browse/{key}",
            counterparty=None,
            text=f"{key}: {summary} · status {status}"
                 + (f" · no movement {(now - updated).days} days" if stale else ""),
            asked_at=datetime.fromisoformat(f["created"].replace("+0000", "+00:00")),
        )
        cls = Classification(
            is_ask=True,
            ask_summary=f"{key} {summary}"[:140],
            counterparty_class="internal",
            deadline=datetime.strptime(f["duedate"], "%Y-%m-%d").date() if f.get("duedate") else None,
            is_blocking=False,   # blocked-link detection is a v1.1 item (SCOPE-TRACE)
            confidence=1.0,
        )
        out.append((cand, cls, stale))
    return out
