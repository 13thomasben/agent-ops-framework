"""Core data models. Everything the pipeline passes around is defined here.

Design rule: stages communicate via these validated models, never loose dicts.
The deal brain must emit a DealVerdict; the pipeline gates recompute the money
math in code and never trust the model's arithmetic.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ListingState(str, Enum):
    """Lifecycle of one listing. Legal transitions live in state.TRANSITIONS."""

    SPOTTED = "spotted"
    SCORED = "scored"
    PASSED = "passed"                    # scored below threshold; kept for dedupe
    WATCHING = "watching"                # good but not great; re-check on price drop
    INQUIRING = "inquiring"              # first message sent, no substantive reply yet
    NEGOTIATING = "negotiating"
    AGREED = "agreed"                    # terms agreed with seller
    AWAITING_APPROVAL = "awaiting_approval"  # card sent to OWNER
    SCHEDULED = "scheduled"              # payment tapped and/or mover booked
    DONE = "done"
    DEAD = "dead"                        # lost/sold/walked/scam — reason in notes


class TransportClass(str, Enum):
    """How the item physically moves. Set by the brain from photos + text."""

    SEDAN = "sedan"          # fits in a car, one person: lamps, stools, small tables
    SUV = "suv"              # bulky but one-person: armchairs, small shelving
    TWO_PERSON = "two_person"  # real furniture: dressers, couches, big desks


class Want(BaseModel):
    """One thing OWNER is hunting for — the natural-language brief IS the spec.

    Soft-fit philosophy: `brief` describes intent (target dimensions, materials,
    vibe); the brain judges holistically like a sharp human buyer. Code enforces
    only the money/geo gates below — never rigid dimension cutoffs.
    """

    slug: str                            # matches the upstream [item.<slug>] name
    brief: str
    value_bar: float = Field(default=0.60, gt=0, le=1.0,
                             description="notify only if all-in ≤ this × fair value")
    max_budget: Optional[float] = Field(default=None, gt=0,
                                        description="soft all-in ceiling, USD")
    search_phrases: list[str] = Field(default_factory=list)
    notes: str = ""
    active: bool = True


class Listing(BaseModel):
    """A marketplace listing as scouted."""

    id: str                              # marketplace item id (from the URL)
    url: str
    title: str
    price: float
    description: str = ""
    photos: list[str] = Field(default_factory=list)
    location: str = ""
    seller_name: str = ""
    condition: str = ""
    want_slug: str = ""                  # which want's search surfaced it
    first_seen: Optional[datetime] = None


class DealVerdict(BaseModel):
    """Structured output of the deal brain. Not vibes — numbers.

    All prices are USD. `opening_offer` and `max_price` feed the negotiation
    playbook; the LLM that produced this verdict never gets to change them
    mid-thread. The pipeline recomputes all_in/value_ratio in code from
    transport_class + distance — the model's own arithmetic is advisory.
    """

    fit: int = Field(ge=0, le=10, description="How well this serves the want's intent")
    quality: int = Field(ge=0, le=10, description="Construction/condition from text+photos")
    fair_value: float = Field(gt=0, description="Realistic local resale value")
    max_price: float = Field(gt=0, description="Walk-away ceiling incl. logistics math")
    opening_offer: float = Field(gt=0)
    scam_flags: list[str] = Field(default_factory=list)
    dimensions_confirmed: bool = False
    summary: str = ""

    # ---- Phase 1 fields (soft-fit, logistics-aware) ----
    transport_class: Optional[TransportClass] = None
    distance_miles: Optional[float] = None      # filled by geo.py, echoed for audit
    delivery_cost: Optional[float] = None       # recomputed in code by the pipeline
    all_in_cost: Optional[float] = None         # price + delivery, recomputed in code
    value_ratio: Optional[float] = None         # all_in / fair_value, recomputed in code
    notify: Optional[bool] = None               # model's recommendation; gates decide
    fit_notes: str = ""                         # dimension/intent reasoning, human-readable
    missing_info: list[str] = Field(default_factory=list)  # what to ask the seller

    @property
    def actionable(self) -> bool:
        """Worth opening a conversation: decent fit/quality and no scam flags."""
        return self.fit >= 7 and self.quality >= 6 and not self.scam_flags


class ThreadMessage(BaseModel):
    """One message in a seller conversation (for state storage + audits)."""

    sender: str                          # "us" | "seller"
    text: str
    at: datetime
    draft: bool = False                  # True in warm-up mode until OWNER taps send
