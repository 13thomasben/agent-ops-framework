"""Payment-link builders — the ONLY payment code this project will ever contain.

Policy (locked July 2026, CLAUDE.md "Hard rules"): the bot prepares a prefilled
payment link; OWNER taps Pay inside the official app. No sanctioned API exists
for sending Venmo/Zelle P2P payments, browser-automating a send trips fraud
models (freezes ~180 days), and P2P sends are irreversible. Do not "improve"
this module into automation.

Link formats (verified July 2026 — Venmo changes these silently, re-test on
device if links stop prefilling):

- Venmo:    https://venmo.com/<username>?txn=pay&amount=<amt>&note=<note>
            Opens the app on mobile with recipient/amount/note prefilled.
            The old venmo://paycharge deep-link scheme is unreliable — not used.
- Cash App: https://cash.app/$<cashtag>/<amount>   (amount prefill only)

Protocol note: for holds, a small Venmo *goods & services* deposit gives buyer
protection (seller pays 2.99%); balance goes out when the mover confirms the
item at the door. See docs/plan.md blocker #5.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote

_VENMO_USER_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")
_CASHTAG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,19}$")
_MAX_NOTE_LEN = 140
_MAX_AMOUNT = Decimal("2000")


class PaymentLinkError(ValueError):
    """Raised when a link can't be built safely (bad handle / silly amount)."""


def _fmt_amount(amount: float | int | str | Decimal) -> str:
    try:
        amt = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception as exc:  # noqa: BLE001 - normalize to our error type
        raise PaymentLinkError(f"unparseable amount: {amount!r}") from exc
    if amt <= 0 or amt > _MAX_AMOUNT:
        raise PaymentLinkError(f"amount {amt} outside sane range (0, {_MAX_AMOUNT}]")
    text = f"{amt:.2f}".rstrip("0").rstrip(".")
    return text


def venmo_pay_link(username: str, amount: float | int | str, note: str) -> str:
    """Build a Venmo prefill link (recipient + amount + note). Human taps Pay."""
    handle = username.strip().lstrip("@")
    if not _VENMO_USER_RE.match(handle):
        raise PaymentLinkError(f"suspicious venmo username: {username!r}")
    clean_note = " ".join(note.split())[:_MAX_NOTE_LEN] or "Marketplace purchase"
    return (
        f"https://venmo.com/{handle}"
        f"?txn=pay&amount={_fmt_amount(amount)}&note={quote(clean_note, safe='')}"
    )


def cashapp_pay_link(cashtag: str, amount: float | int | str) -> str:
    """Build a Cash App prefill link (amount only — Cash App ignores notes)."""
    tag = cashtag.strip().lstrip("$")
    if not _CASHTAG_RE.match(tag):
        raise PaymentLinkError(f"suspicious cashtag: {cashtag!r}")
    return f"https://cash.app/${tag}/{_fmt_amount(amount)}"
