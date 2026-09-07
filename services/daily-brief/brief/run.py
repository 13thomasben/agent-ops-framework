"""The morning pipeline, per active user:

  sync roster → pull (A,B,C,D) → filter → classify → UPSERT STATE →
  closure sweep → tier + score → select (cap 15) → render → send →
  freeze numbering → log the run (checklist item 12).

Order note: closure runs BEFORE selection so this morning's brief never shows
a loop the sources already prove closed — but AFTER upsert, so a brand-new ask
and its same-morning reply cancel out correctly.

CLI:
  python -m brief.run --user sponsor --dry-run     # HTML to out/, no send
  python -m brief.run --all-active                 # the 6:15 production entry
  python -m brief.run --reply-close                # process 'close N' replies
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import date
from pathlib import Path

from . import alerts, classify, closure, config, credentials, render, reply_close, score, store
from .pulls import email_inbound, email_outbound, graph, jira_assigned, slack_inbound, slack_outbound

OUT_DIR = Path(os.environ.get("BRIEF_OUT_DIR", Path(__file__).parent.parent / "out"))


def _dry() -> bool:
    return os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")


def run_user(user: dict, send: bool = True) -> dict:
    """Full pipeline for one person. Raises on hard failure (caller alerts)."""
    counts: dict = {"blocks": {}, "classifier": {"kept": 0, "dropped": 0}, "closures": {}}
    lookbacks = config.weights()["brief"]["lookback_days"]

    # -------- pulls (each source failure is fatal for the run: a brief built
    # on partial sources would silently under-report, which is worse than no
    # brief plus a loud alert) --------
    snapshot = graph.MailboxSnapshot(user["email"], lookbacks["email_inbound"]).load()
    slack_token: str | None = None
    try:
        slack_token = credentials.slack_user_token(user["email"])
    except credentials.MissingConsent:
        if user["key"] != "owner":  # pre-consent dry runs shouldn't hard-fail on Slack
            raise

    candidates = []
    candidates += [(c, None, False) for c in email_inbound.pull(user, snapshot)]
    candidates += [(c, None, False) for c in email_outbound.pull(user, snapshot)]
    if slack_token:
        candidates += [(c, None, False) for c in
                       slack_inbound.pull(user, slack_token, lookbacks["slack_inbound"])]
        candidates += [(c, None, False) for c in
                       slack_outbound.pull(user, slack_token, lookbacks["outbound"])]
    jira_rows = jira_assigned.pull(user) if user.get("jira_account_id") not in (None, "", "TBD") else []
    candidates += jira_rows

    for block in "ABCD":
        counts["blocks"][block] = sum(1 for c, _, _ in candidates if c.block == block)

    # -------- classify (blocks A/B/D; C is definitional) + upsert --------
    for cand, cls, stale in candidates:
        if cls is None:
            cls = classify.classify(cand)
            if cls is None:
                counts["classifier"]["dropped"] += 1
                continue
            counts["classifier"]["kept"] += 1
        store.upsert_item(cand, cls, stale_flag=stale)

    # -------- closure sweep over ALL open items (incl. prior days) --------
    counts["closures"] = closure.run_for_user(user, snapshot, slack_token)

    # -------- select, render --------
    selection = score.select(store.open_items(user["email"]))
    store.update_scores(selection["shown"] + selection["waiting"])
    subject, html, ordered_ids = render.render(selection)
    counts["shown"] = len(selection["shown"])
    counts["not_shown"] = selection["not_shown"]
    counts["waiting"] = len(selection["waiting"])

    # -------- anomaly check (spec: zero items for a user who had items) ------
    prev = store.latest_brief(user["email"])
    if prev and prev["shown"] > 0 and counts["shown"] == 0 and counts["waiting"] == 0:
        alerts.zero_items_anomaly(user["email"], prev["shown"])

    # -------- send + freeze numbering --------
    if send and not _dry():
        graph.send_mail(config.ops()["brief_mailbox"], user["email"], subject, html)
    else:
        OUT_DIR.mkdir(exist_ok=True)
        out = OUT_DIR / f"{date.today().isoformat()}-{user['key']}.html"
        out.write_text(html)
        counts["dry_run_file"] = str(out)
    store.record_brief(user["email"], subject, ordered_ids,
                       selection["not_shown"], counts["waiting"], html)
    return counts


def daily(users: list[dict]) -> int:
    """Run every user independently; one person's failure never blocks
    another's brief. Exit code = number of failed users."""
    store.sync_roster(config.people())
    failures = 0
    for user in users:
        run_id = store.start_run("daily", user["email"])
        try:
            counts = run_user(user)
            status = "ok" if (counts["shown"] or counts["waiting"]) else "no_op"
            store.finish_run(run_id, status, counts)
            print(f"[{user['key']}] {status}: {json.dumps(counts['blocks'])} "
                  f"shown={counts.get('shown')} waiting={counts.get('waiting')}")
        except Exception as e:
            failures += 1
            store.finish_run(run_id, "error", {}, f"{e}\n{traceback.format_exc()}")
            alerts.run_failed(user["email"], str(e))
            print(f"[{user['key']}] ERROR: {e}", file=sys.stderr)
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description="Daily Accountability Brief")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--user", help="roster key or email — run one person")
    g.add_argument("--all-active", action="store_true", help="run every active roster user")
    g.add_argument("--reply-close", action="store_true", help="process reply-to-close inbox")
    ap.add_argument("--dry-run", action="store_true", help="render to out/, do not send")
    args = ap.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "1"

    if args.reply_close:
        run_id = store.start_run("reply_close", None)
        try:
            counts = reply_close.run()
            store.finish_run(run_id, "ok" if counts["processed"] else "no_op", counts)
            print(json.dumps(counts))
        except Exception as e:
            store.finish_run(run_id, "error", {}, str(e))
            alerts.dm_owner(f":rotating_light: reply-to-close poller failed: {e}")
            raise
        return

    users = config.people(active_only=True) if args.all_active else [config.person(args.user)]
    if not users:
        print("no active users in roster — nothing to do")
        return
    sys.exit(min(daily(users), 1))


if __name__ == "__main__":
    main()
