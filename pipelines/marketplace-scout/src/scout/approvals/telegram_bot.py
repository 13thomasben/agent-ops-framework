"""Phase 1 — OWNER's phone remote, via the raw Telegram Bot API (httpx only).

Why raw API instead of python-telegram-bot: we need exactly four calls
(sendPhoto, sendMessage, getUpdates, answerCallbackQuery) and a synchronous
loop; a framework adds an async runtime for no benefit. httpx is imported
lazily so tests stay hermetic — card FORMATTING is pure and fully tested.

Buttons on a scored card: [Watch] [Kill] [Draft opener]. "Draft opener"
generates a copy-paste message for OWNER to send THEMSELVES from Messenger —
Phase 1 automates zero seller contact (see CLAUDE.md hard rules); this is the
latency-killer bridge until the Phase 2 negotiator earns trust.
"""

from __future__ import annotations

import html
import os
from typing import Optional

from ..schema import DealVerdict, Listing, Want

API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "")


# ---------------------------------------------------------------------------
# Pure formatting (tested)
# ---------------------------------------------------------------------------

def format_card(listing: Listing, verdict: DealVerdict, want: Want) -> str:
    """HTML-mode card text. Everything user-generated is escaped."""
    t = html.escape(listing.title)
    miles = (f"{verdict.distance_miles} mi" if verdict.distance_miles is not None
             else "distance unknown")
    delivery = (f"${verdict.delivery_cost:.0f}" if verdict.delivery_cost is not None
                else "?")
    all_in = (f"${verdict.all_in_cost:.0f}" if verdict.all_in_cost is not None
              else "?")
    ratio = (f"{verdict.value_ratio:.0%} of value" if verdict.value_ratio is not None
             else "ratio n/a")
    lines = [
        f"<b>{t}</b> — ${listing.price:.0f} <i>({html.escape(want.slug)})</i>",
        f"fit {verdict.fit}/10 · quality {verdict.quality}/10 · fair ~${verdict.fair_value:.0f}",
        f"all-in {all_in} ({delivery} {html.escape(verdict.transport_class.value if verdict.transport_class else '?')} · {miles}) → <b>{ratio}</b>",
        f"plan: open ${verdict.opening_offer:.0f}, walk above ${verdict.max_price:.0f}",
    ]
    if verdict.fit_notes:
        lines.append(f"<i>{html.escape(verdict.fit_notes)}</i>")
    if verdict.missing_info:
        lines.append("ask seller: " + html.escape("; ".join(verdict.missing_info)))
    if verdict.scam_flags:
        lines.append("⚠ " + html.escape(", ".join(verdict.scam_flags)))
    lines.append(html.escape(verdict.summary))
    lines.append(listing.url)
    return "\n".join(lines)


def buttons_for(listing_id: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "👀 Watch", "callback_data": f"watch:{listing_id}"},
        {"text": "🗑 Kill", "callback_data": f"kill:{listing_id}"},
        {"text": "✍️ Draft opener", "callback_data": f"draft:{listing_id}"},
    ]]}


# ---------------------------------------------------------------------------
# API calls (lazy httpx; every call is best-effort)
# ---------------------------------------------------------------------------

def _call(method: str, payload: dict) -> Optional[dict]:  # pragma: no cover - network
    import httpx

    token = _token()
    if not token:
        return None
    try:
        resp = httpx.post(API.format(token=token, method=method), json=payload,
                          timeout=20)
        data = resp.json()
        return data if data.get("ok") else None
    except Exception:
        return None


def send_card(listing: Listing, verdict: DealVerdict, want: Want) -> None:  # pragma: no cover
    text = format_card(listing, verdict, want)
    payload = {"chat_id": _chat_id(), "parse_mode": "HTML",
               "reply_markup": buttons_for(listing.id)}
    if listing.photos:
        _call("sendPhoto", {**payload, "photo": listing.photos[0],
                            "caption": text[:1024]})
    else:
        _call("sendMessage", {**payload, "text": text[:4000]})


def send_text(text: str) -> None:  # pragma: no cover
    _call("sendMessage", {"chat_id": _chat_id(), "text": text[:4000]})


def poll_callbacks(offset: int = 0) -> tuple[list[tuple[str, str]], int]:  # pragma: no cover
    """Return ([(action, listing_id), ...], next_offset). Ack every callback."""
    data = _call("getUpdates", {"offset": offset, "timeout": 0,
                                "allowed_updates": ["callback_query"]})
    actions: list[tuple[str, str]] = []
    next_offset = offset
    for update in (data or {}).get("result", []):
        next_offset = max(next_offset, update["update_id"] + 1)
        cq = update.get("callback_query")
        if not cq:
            continue
        _call("answerCallbackQuery", {"callback_query_id": cq["id"]})
        raw = cq.get("data", "")
        if ":" in raw:
            action, listing_id = raw.split(":", 1)
            actions.append((action, listing_id))
    return actions, next_offset


def format_agreed_card(listing: Listing, agreed_price: float, venmo_link: str,
                       lugg_pretty: str, windows: str) -> str:
    """The two-tap moment (Phase 3 wiring)."""
    return (
        f"AGREED: {listing.title} at ${agreed_price:.0f}\n"
        f"1) Pay (prefilled): {venmo_link}\n"
        f"2) Book mover {lugg_pretty} — proposed: {windows}\n"
        f"Payment goes out when the mover confirms at the door."
    )
