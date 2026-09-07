"""Lugg cost math (real) + booking prefill (Phase 3 stub).

Rates from https://lugg.com/help/pricing/how-much-does-a-lugg-cost (July 2026),
"Lugg Pickup" tier (pickup truck + 2 luggers — right size for a dresser):
$38 base + $2.24/mile + $1.62/labor-minute. Lugg's own example: an 8-mile
Facebook Marketplace run ≈ $96 before booking fee. Re-check rates quarterly;
they vary by metro and demand.

Booking has no public self-serve API (partner-gated: https://docs.lugg.com/).
Phase 3 automates the guest quote flow and hands OWNER a prefilled booking to
confirm — the booking tap is OWNER's, permanently (CLAUDE.md hard rules).
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_FEE = 38.00
PER_MILE = 2.24
PER_LABOR_MINUTE = 1.62
DEFAULT_LABOR_MINUTES = 25  # load + unload a dresser, two luggers


@dataclass(frozen=True)
class LuggEstimate:
    miles: float
    labor_minutes: float
    total: float

    @property
    def pretty(self) -> str:
        return f"~${self.total:.0f} (Lugg Pickup, {self.miles:.0f} mi)"


def estimate(miles: float, labor_minutes: float = DEFAULT_LABOR_MINUTES) -> LuggEstimate:
    """Ballpark a dresser move. Used by the deal brain's logistics math."""
    if miles < 0 or labor_minutes < 0:
        raise ValueError("miles and labor_minutes must be non-negative")
    total = BASE_FEE + PER_MILE * miles + PER_LABOR_MINUTE * labor_minutes
    return LuggEstimate(miles=miles, labor_minutes=labor_minutes, total=round(total, 2))


def booking_prefill_url(pickup_address: str, dropoff_address: str) -> str:
    """Phase 3 TODO: verify lugg.com guest-quote URL params via a manual run,
    then build the deepest prefill we can. Until then, the card links the
    plain quote page and OWNER pastes addresses."""
    raise NotImplementedError("Phase 3 — verify Lugg quote-flow params first")
