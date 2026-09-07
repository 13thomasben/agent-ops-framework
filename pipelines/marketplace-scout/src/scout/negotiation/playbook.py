"""Deterministic offer ladder. The LLM writes the words; this module picks every number.

Phase 2 wiring: messenger.py surfaces seller messages, an LLM extracts the
seller's current price + intent, and `decide()` returns the only actions the
system may take. Anything decide() can't classify becomes ESCALATE (OWNER gets
a Telegram ping). The model never chooses an amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..schema import DealVerdict


class Action(str, Enum):
    ACCEPT = "accept"
    COUNTER = "counter"
    WALK = "walk"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class Decision:
    action: Action
    amount: float | None = None
    why: str = ""


@dataclass(frozen=True)
class OfferPlan:
    """Precomputed ladder for one listing. Built once from the verdict."""

    opening: int
    target: int          # the "happy" price — accept anything at or below this
    ceiling: int         # absolute walk-away, never exceeded
    offers: tuple[int, ...]  # ascending, offers[0]=opening, offers[-1]=ceiling


def _round5(x: float) -> int:
    return int(5 * round(x / 5.0))


def build_plan(verdict: DealVerdict, asking_price: float) -> OfferPlan:
    """Ladder from an opening lowball to the ceiling in shrinking concessions.

    Ceiling is the *lesser* of the verdict's max_price and the asking price —
    we never offer above ask. Concessions shrink (40/70/90/100% of the gap)
    so movement signals "almost done" the way human hagglers expect.
    """
    ceiling = _round5(min(verdict.max_price, asking_price))
    if ceiling <= 0:
        raise ValueError("ceiling must be positive")
    opening = min(_round5(0.70 * ceiling), ceiling)
    if opening <= 0:
        opening = ceiling
    gap = ceiling - opening
    raw = [opening + gap * f for f in (0.0, 0.4, 0.7, 0.9, 1.0)]
    offers: list[int] = []
    for value in raw:
        step = min(_round5(value), ceiling)
        if not offers or step > offers[-1]:
            offers.append(step)
    if offers[-1] != ceiling:
        offers.append(ceiling)
    target = offers[-2] if len(offers) >= 2 else ceiling
    return OfferPlan(opening=opening, target=target, ceiling=ceiling, offers=tuple(offers))


def decide(seller_price: float, plan: OfferPlan, offers_made: int) -> Decision:
    """Next move given the seller's current stated price.

    `offers_made` counts how many rungs of plan.offers we've already used.
    """
    if seller_price <= 0:
        return Decision(Action.ESCALATE, why="could not parse a price from the thread")

    if seller_price <= plan.target:
        return Decision(Action.ACCEPT, amount=float(seller_price), why="at/below target")

    if seller_price <= plan.ceiling:
        # Within our ceiling but above target: one more nudge if we have rungs
        # left, otherwise take the deal — it's still inside the verdict.
        if offers_made < len(plan.offers):
            nxt = plan.offers[min(offers_made, len(plan.offers) - 1)]
            counter = min(max(nxt, _round5((nxt + seller_price) / 2)), plan.ceiling)
            return Decision(Action.COUNTER, amount=float(counter), why="inside ceiling, nudging")
        return Decision(Action.ACCEPT, amount=float(seller_price), why="ceiling-inclusive accept")

    # Seller is above our ceiling.
    if offers_made < len(plan.offers):
        nxt = plan.offers[min(offers_made, len(plan.offers) - 1)]
        return Decision(Action.COUNTER, amount=float(nxt), why="seller above ceiling, laddering")
    return Decision(Action.WALK, why=f"seller {seller_price:.0f} > ceiling {plan.ceiling}")
