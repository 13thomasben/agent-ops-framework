"""Phase 1 pipeline: upstream cache → geo → brain → CODE GATES → Telegram.

The model recommends; these gates decide. A notification fires only when ALL
hold (see `gates`):
  1. no scam flags
  2. all-in cost (price + delivery, computed in code) ≤ want.value_bar × fair_value
  3. under want.max_budget, if set
  4. fit ≥ 6 — soft-fit means the model already reasoned about tolerances;
     this floor just keeps "technically could work" listings off the phone
  5. never notified for this (listing, price) before — price drops re-qualify

Run it alongside the upstream monitor:  `scout run`  (or --once).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from .geo import Geo
from .schema import DealVerdict, Listing, ListingState, Want
from .state import ListingStore
from .transport import delivery_quote
from .wants import load_wants


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def apply_money_math(verdict: DealVerdict, listing: Listing,
                     distance_miles: Optional[float]) -> DealVerdict:
    """Recompute delivery/all-in/ratio in code — never trust model arithmetic."""
    if verdict.transport_class is None:
        return verdict
    quote = delivery_quote(verdict.transport_class, distance_miles)
    verdict.delivery_cost = quote.cost
    verdict.all_in_cost = round(listing.price + quote.cost, 2)
    verdict.value_ratio = (round(verdict.all_in_cost / verdict.fair_value, 3)
                           if verdict.fair_value else None)
    verdict.distance_miles = distance_miles
    return verdict


def gates(verdict: DealVerdict, want: Want) -> GateResult:
    reasons: list[str] = []
    if verdict.scam_flags:
        reasons.append(f"scam flags: {', '.join(verdict.scam_flags)}")
    if verdict.value_ratio is None:
        reasons.append("value ratio not computable (missing transport class or fair value)")
    elif verdict.value_ratio > want.value_bar:
        reasons.append(f"value ratio {verdict.value_ratio:.2f} > bar {want.value_bar:.2f}")
    if want.max_budget and verdict.all_in_cost and verdict.all_in_cost > want.max_budget:
        reasons.append(f"all-in ${verdict.all_in_cost:.0f} > budget ${want.max_budget:.0f}")
    if verdict.fit < 6:
        reasons.append(f"fit {verdict.fit}/10 below floor")
    return GateResult(passed=not reasons, reasons=reasons)


@dataclass
class Pipeline:
    """Dependency-injected so every piece is testable without network."""

    store: ListingStore
    geo: Geo
    wants: list[Want]
    score_fn: Callable[..., DealVerdict]          # brain.score_listing signature
    notify_fn: Callable[[Listing, DealVerdict, Want], None]
    log: Callable[[str], None] = print

    def process(self, listing: Listing) -> Optional[DealVerdict]:
        want = next((w for w in self.wants if w.slug == listing.want_slug), None)
        if want is None:
            return None
        key = f"{listing.id}@{listing.price:.0f}"
        if self.store.was_processed(key):
            return None
        self.store.upsert(listing)
        miles = self.geo.miles_from_home(listing.location) if listing.location else None
        from .transport import cost_menu  # local import avoids cycle at module load
        verdict = self.score_fn(listing, want, distance_miles=miles,
                                cost_menu=cost_menu(miles))
        verdict = apply_money_math(verdict, listing, miles)
        self.store.mark_processed(key)
        try:
            self.store.transition(listing.id, ListingState.SCORED)
        except Exception:
            pass  # re-scored price drop: row may already be past SCORED
        self.store.attach_verdict(listing.id, verdict.model_dump_json())
        result = gates(verdict, want)
        if result.passed:
            self.log(f"NOTIFY {listing.id}: {verdict.summary[:80]}")
            self.notify_fn(listing, verdict, want)
        else:
            self.log(f"pass {listing.id}: {'; '.join(result.reasons)[:120]}")
            try:
                self.store.transition(listing.id, ListingState.PASSED,
                                      note="; ".join(result.reasons))
            except Exception:
                pass
        return verdict

    def run_once(self, listings: Iterable[Listing]) -> int:
        n = 0
        for listing in listings:
            if self.process(listing) is not None:
                n += 1
        return n


def run_loop(pipeline: Pipeline, source_fn: Callable[[], Iterable[Listing]],
             poll_seconds: int = 300,
             callbacks_fn: Optional[Callable[[], None]] = None) -> None:  # pragma: no cover
    """Forever: score new cache entries, service Telegram buttons, sleep.

    poll_seconds=300 only polls OUR OWN local cache/Telegram — it makes no
    Facebook traffic whatsoever, so it does not violate the ≥30-min rule.
    """
    while True:
        try:
            pipeline.run_once(source_fn())
            if callbacks_fn:
                callbacks_fn()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            pipeline.log(f"pipeline error (continuing): {exc!r}")
        time.sleep(poll_seconds)
