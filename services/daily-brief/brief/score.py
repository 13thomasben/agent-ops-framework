"""Checklist item 8 — tiers and scoring (spec §4). Tier is what the reader
sees; score only orders items inside a tier. All weights come from
config/weights.yaml so tuning never touches code."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import config

TIER_ORDER = ["blocking", "overdue", "today", "aging"]
EXTERNAL = {"customer", "lender", "oem"}


def business_days_between(start: date, end: date) -> int:
    """Whole business days from start to end (Sat/Sun excluded).
    Holiday awareness is a v2 item alongside calendar-aware suppression."""
    if end <= start:
        return 0
    days, cur = 0, start
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def _window_bd(item: dict) -> int:
    w = config.weights()["response_windows_business_days"]
    cls, source = item["counterparty_class"], item["source"]
    if source == "jira":
        return w["ticket"]
    if source == "slack":
        return w["internal_dm"]
    if cls in EXTERNAL:
        return w["external_email"]
    if cls == "vendor":
        return w["vendor_email"]
    return w["internal_email"]


def assign_tier(item: dict, today: date | None = None) -> str:
    today = today or date.today()
    first_seen = item["first_seen"]
    if isinstance(first_seen, datetime):
        first_seen = first_seen.astimezone(timezone.utc).date()
    bd_open = business_days_between(first_seen, today)
    deadline = item.get("deadline")

    # Blocking: explicit blocking language (classifier) or a repeated ask on
    # the same thread (spec: second and third asks escalate hard).
    if item.get("is_blocking") or (item.get("repeat_count") or 1) >= 2:
        return "blocking"
    if deadline and deadline < today:
        return "overdue"
    if bd_open > _window_bd(item):
        return "overdue"
    if deadline == today:
        return "today"
    return "aging"


def score_item(item: dict, today: date | None = None) -> float:
    today = today or date.today()
    s = config.weights()["score"]
    first_seen = item["first_seen"]
    if isinstance(first_seen, datetime):
        first_seen = first_seen.astimezone(timezone.utc).date()

    total = (today - first_seen).days * s["days_open_weight"]          # 1. days open, heaviest
    total += s["counterparty_class"].get(item["counterparty_class"], 0)  # 2. counterparty class
    hay = f"{item.get('counterparty') or ''} {item.get('ask_summary') or ''}".lower()
    if any(d.lower() in hay for d in config.weights().get("named_active_deals", [])):
        total += s["deal_linkage_bonus"]                                # 3. deal linkage
    sender = (item.get("counterparty") or "").lower()
    if any(l.lower() in sender for l in config.weights().get("leadership", [])):
        total += s["seniority_bonus"]                                   # 4. sender seniority
    total += ((item.get("repeat_count") or 1) - 1) * s["repeat_ask_bonus"]  # 5. repeat asks
    return round(total, 1)


def select(items: list[dict], today: date | None = None) -> dict:
    """Tier + score every open item, then apply the spec's reading contract:
    blocks A–C capped at max_items ordered tier-then-score, block D uncapped
    but compact. Returns everything the renderer and store need."""
    today = today or date.today()
    for it in items:
        it["tier"] = assign_tier(it, today)
        it["score"] = score_item(it, today)

    abc = [i for i in items if i["block"] in ("A", "B", "C")]
    d = [i for i in items if i["block"] == "D"]

    abc.sort(key=lambda i: (TIER_ORDER.index(i["tier"]), -i["score"]))
    d.sort(key=lambda i: -(i.get("days_open") or 0))

    cap = config.weights()["brief"]["max_items"]
    shown, hidden = abc[:cap], abc[cap:]
    return {
        "shown": shown,
        "not_shown": len(hidden),
        "waiting": d,
        "counts": {
            "blocking": sum(1 for i in shown if i["tier"] == "blocking"),
            "overdue": sum(1 for i in shown if i["tier"] == "overdue"),
            "today": sum(1 for i in shown if i["tier"] == "today"),
            "aging": sum(1 for i in shown if i["tier"] == "aging"),
            "total_open": len(abc),
        },
    }
