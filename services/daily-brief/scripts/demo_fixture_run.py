"""End-to-end fixture demo: migrate a scratch DB, seed the §6 example as real
state rows, run the actual scorer + renderer, emit the HTML brief.

  DATABASE_URL=postgresql:///brief_demo \\
  BRIEF_CONFIG_DIR=fixtures/demo-config \\
  python scripts/demo_fixture_run.py

No credentials, no network. What this proves: state persistence semantics,
tiering, business-day windows, scoring, the cap, numbering, and the renderer —
everything except the live pulls."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml  # noqa: E402

from brief import config, render, score, store  # noqa: E402
from brief.models import stable_id  # noqa: E402
from db.migrate import migrate  # noqa: E402

DEMO_USER = "sponsor@acme.example.com"


def seed() -> None:
    store.sync_roster(config.people())
    fixtures = yaml.safe_load((Path(__file__).parent.parent / "fixtures/section6.yaml").read_text())
    now = datetime.now(timezone.utc)
    with store.conn() as c:
        c.execute("truncate items, brief_items, briefs, runs, reply_close_log cascade")
        for f in fixtures["items"]:
            first_seen = now - timedelta(days=f["days_ago"])
            c.execute(
                """insert into items (id, user_email, block, source, source_id, permalink,
                                      ask_summary, counterparty, counterparty_class, is_blocking,
                                      deadline, confidence, repeat_count, stale_flag,
                                      first_seen, last_ask_at)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    stable_id(DEMO_USER, f["source"], f["source_id"]),
                    DEMO_USER, f["block"], f["source"], f["source_id"],
                    f.get("permalink"), f["ask_summary"], f.get("counterparty"),
                    f.get("counterparty_class", "unknown"), f.get("is_blocking", False),
                    now.date() if f.get("deadline_today") else None,
                    0.92, f.get("repeat_count", 1), f.get("stale", False),
                    first_seen, first_seen,
                ),
            )


def main() -> None:
    print("migrating:", migrate() or "up to date")
    seed()
    items = store.open_items(DEMO_USER)
    print(f"seeded {len(items)} open items for the demo sponsor")

    selection = score.select(items)
    subject, html, ordered = render.render(selection)
    store.update_scores(selection["shown"] + selection["waiting"])
    brief_id = store.record_brief(DEMO_USER, subject, ordered,
                                  selection["not_shown"], len(selection["waiting"]), html)

    out = Path(__file__).parent.parent / "out" / "demo-brief.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)

    print(f"subject : {subject}")
    print(f"tiers   : {selection['counts']}")
    print(f"shown {len(selection['shown'])} · not shown {selection['not_shown']} · waiting {len(selection['waiting'])}")
    print(f"brief_id {brief_id} recorded with frozen numbering 1..{len(ordered)}")
    print(f"html    : {out}")

    # prove reply-to-close resolves against the frozen numbering
    from brief.reply_close import parse_positions
    b = store.latest_brief(DEMO_USER)
    positions = parse_positions("close 4, 7")
    closed = [b["positions"][p] for p in positions]
    for item_id in closed:
        store.close_item(item_id, "manual", "demo reply-to-close")
    remaining = {i["id"] for i in store.open_items(DEMO_USER)}
    assert not (set(closed) & remaining), "manual close failed"
    print(f'reply-to-close "close 4, 7" → closed items {positions}, {len(remaining)} remain open')


if __name__ == "__main__":
    os.environ.setdefault("DATABASE_URL", "postgresql:///brief_demo")
    main()
