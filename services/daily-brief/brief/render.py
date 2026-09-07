"""Checklist item 9 — the HTML renderer. Mobile-first single column, inline
CSS, no external assets, no images (spec §5). Every item carries its deep link
and its visible day counter. Numbering is continuous through the Waiting
section so every number on the page is closeable by reply."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config, score as score_mod

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)

TIER_TITLES = {
    "blocking": ("BLOCKING SOMEONE", "#a03518"),
    "overdue": ("OVERDUE", "#8a4b08"),
    "today": ("TODAY", "#1a56a0"),
    "aging": ("AGING", "#3d3d46"),
}

SOURCE_LABELS = {"email": "Email · reply", "slack": "Slack · open thread"}


def _counter(item: dict, today: date) -> str:
    days = item.get("days_open") or 0
    deadline = item.get("deadline")
    if item["tier"] == "today":
        return "due today"
    if deadline and deadline < today:
        return f"open {days} days, due {deadline.strftime('%b %-d')}"
    if item["tier"] == "overdue":
        expected = score_mod._window_bd(item)
        return f"open {days} days, expected {expected}"
    return f"open {days} day{'s' if days != 1 else ''}"


def _source_label(item: dict) -> str:
    if item["source"] == "jira":
        return f"Jira · open {item['source_id']}"
    return SOURCE_LABELS.get(item["source"], item["source"])


def _detail(item: dict) -> str:
    parts = []
    if item.get("counterparty"):
        parts.append(item["counterparty"].split("<")[0].strip())
    if (item.get("repeat_count") or 1) >= 2:
        parts.append(f"asked {item['repeat_count']} times on this thread")
    if item.get("stale_flag"):
        parts.append("no status change or comment in 7+ days")
    return " — ".join(parts)


def subject_line(counts: dict, today: date) -> str:
    day = f"{today.strftime('%A %B')} {today.day}"
    segs = []
    if counts["blocking"]:
        segs.append(f"{counts['blocking']} blocking")
    if counts["overdue"]:
        segs.append(f"{counts['overdue']} overdue")
    if not segs:
        segs = [f"{counts['total_open']} open"] if counts["total_open"] else ["all clear"]
    return f"Your open loops, {day} - " + ", ".join(segs)


def render(selection: dict, today: date | None = None) -> tuple[str, str, list[str]]:
    """Returns (subject, html, ordered_item_ids). ordered_item_ids maps
    printed position → item id (position = index+1), frozen into brief_items
    so reply-to-close resolves against exactly what was printed."""
    today = today or date.today()
    shown, waiting = selection["shown"], selection["waiting"]
    counts = selection["counts"]

    sections, ordered_ids, pos = [], [], 0
    for tier in score_mod.TIER_ORDER:
        tier_items = [i for i in shown if i["tier"] == tier]
        if not tier_items:
            continue
        title, color = TIER_TITLES[tier]
        rows = []
        for it in tier_items:
            pos += 1
            ordered_ids.append(it["id"])
            rows.append({
                "position": pos,
                "title": it["ask_summary"],
                "counter": _counter(it, today),
                "detail": _detail(it),
                "link": it.get("permalink"),
                "source_label": _source_label(it),
            })
        section = {"title": title, "color": color, "rows": rows,
                   "compact": tier == "aging", "after_note": None}
        if tier == "aging" and selection["not_shown"]:
            section["after_note"] = f"{selection['not_shown']} more not shown."
        sections.append(section)
    if selection["not_shown"] and not any(s["title"] == "AGING" for s in sections):
        sections.append({"title": "AGING", "color": TIER_TITLES["aging"][1], "rows": [],
                         "compact": True, "after_note": f"{selection['not_shown']} more not shown."})

    waiting_rows = []
    for it in waiting:
        pos += 1
        ordered_ids.append(it["id"])
        days = it.get("days_open") or 0
        waiting_rows.append({
            "position": pos,
            "counterparty": (it.get("counterparty") or "?").split("<")[0].strip(),
            "title": it["ask_summary"],
            "counter": f"asked {days} day{'s' if days != 1 else ''} ago, no reply",
            "link": it.get("permalink"),
        })

    count_segments = []
    for k in ("blocking", "overdue"):
        if counts[k]:
            count_segments.append(f"{counts[k]} {k}")
    count_segments.append(f"{counts['total_open']} total")

    subject = subject_line(counts, today)
    html = _env.get_template("brief.html.j2").render(
        subject=subject,
        date_line=f"{today.strftime('%A, %B')} {today.day}",
        count_segments=count_segments,
        sections=sections,
        waiting=waiting_rows,
        generated=today.isoformat(),
    )
    return subject, html, ordered_ids
