"""Delivery-cost model — the number the value gate uses, computed in code.

Tiers (July 2026 reality, see docs/plan.md):
- SEDAN items within courier range: Uber Connect-class courier (≤30 lb, fits in
  a car). Flat-ish $25. Nothing Uber offers moves real furniture.
- SUV items: bulky one-person loads — courier XL / pickup-truck gig, ~$45.
- TWO_PERSON items: Lugg Pickup tier (2 movers), rate math in closing/lugg.py.
- Self pickup: $0 when it's close and OWNER can carry it (sedan-class by
  default — set SCOUT_SELF_CLASSES="sedan,suv" if the car fits more).

Unknown distance NEVER counts as close: we price it like a 12-mile mover run
and let the verdict carry the uncertainty.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .closing.lugg import estimate as lugg_estimate
from .schema import TransportClass

COURIER_FLAT = 25.0
COURIER_MAX_MILES = 15.0
SUV_FLAT = 45.0
SELF_RADIUS_MILES = 10.0
UNKNOWN_DISTANCE_ASSUMPTION = 12.0


def _self_classes() -> set[TransportClass]:
    raw = os.environ.get("SCOUT_SELF_CLASSES", "sedan")
    out = set()
    for part in raw.split(","):
        part = part.strip().lower()
        if part:
            out.add(TransportClass(part))
    return out


@dataclass(frozen=True)
class DeliveryQuote:
    cost: float
    method: str          # "self pickup" | "courier" | "courier-xl" | "movers (lugg-class)"
    distance_known: bool


def delivery_quote(tclass: TransportClass, miles: float | None) -> DeliveryQuote:
    known = miles is not None
    m = miles if miles is not None else UNKNOWN_DISTANCE_ASSUMPTION
    if known and m <= SELF_RADIUS_MILES and tclass in _self_classes():
        return DeliveryQuote(0.0, "self pickup", True)
    if tclass is TransportClass.SEDAN:
        if m <= COURIER_MAX_MILES:
            return DeliveryQuote(COURIER_FLAT, "courier", known)
        return DeliveryQuote(SUV_FLAT, "courier-xl", known)
    if tclass is TransportClass.SUV:
        if m <= COURIER_MAX_MILES:
            return DeliveryQuote(SUV_FLAT, "courier-xl", known)
        return DeliveryQuote(round(lugg_estimate(m).total * 0.85, 2),
                             "movers (single + van)", known)
    return DeliveryQuote(lugg_estimate(m).total, "movers (lugg-class)", known)


def cost_menu(miles: float | None) -> dict[str, float]:
    """All three tiers for the brain's prompt, so it can reason about all-in."""
    return {tc.value: delivery_quote(tc, miles).cost for tc in TransportClass}
