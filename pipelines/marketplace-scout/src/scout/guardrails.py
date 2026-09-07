"""Hard operating limits, enforced in code — the model never sees these as suggestions.

Philosophy (CLAUDE.md "Hard rules"): the LLM writes prose inside rails it cannot
cross. Price ceilings, message pacing, active hours, and the human-tap rule for
money are all plain Python here. If a future change makes any of these
model-controllable, that change is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

#: Money movement and mover bookings always require OWNER's tap. This is a
#: constant on purpose — there is deliberately no config knob for it.
MONEY_ALWAYS_NEEDS_HUMAN: bool = True


def require_human_for_money() -> bool:
    """Always True, permanently. See docs/plan.md blocker #3."""
    return MONEY_ALWAYS_NEEDS_HUMAN


@dataclass(frozen=True)
class Guardrails:
    """Session-wide caps. Defaults are deliberately conservative — loosen with care."""

    max_item_price: float = 300.0            # global ceiling regardless of verdict
    weekly_spend_cap: float = 500.0
    max_new_conversations_per_day: int = 5   # keep the account boring
    max_messages_per_thread: int = 30
    min_seconds_between_sends: float = 45.0  # typing-speed pacing
    active_start: time = time(9, 0)          # local hunting hours
    active_end: time = time(21, 30)
    tz: str = "America/New_York"

    # ---- checks -----------------------------------------------------------

    def within_active_hours(self, now: Optional[datetime] = None) -> bool:
        tz = ZoneInfo(self.tz)
        local = (now or datetime.now(tz)).astimezone(tz)
        return self.active_start <= local.time() <= self.active_end

    def allow_offer(self, amount: float, verdict_max_price: float) -> tuple[bool, str]:
        """An offer may never exceed the verdict ceiling OR the global cap."""
        ceiling = min(verdict_max_price, self.max_item_price)
        if amount > ceiling:
            return False, f"offer {amount:.2f} exceeds ceiling {ceiling:.2f}"
        if amount <= 0:
            return False, "offer must be positive"
        return True, "ok"

    def allow_new_conversation(self, started_today: int) -> tuple[bool, str]:
        if started_today >= self.max_new_conversations_per_day:
            return False, (
                f"daily new-conversation cap reached "
                f"({self.max_new_conversations_per_day})"
            )
        return True, "ok"

    def allow_send(
        self,
        seconds_since_last_send: float,
        messages_in_thread: int,
        now: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        if not self.within_active_hours(now):
            return False, "outside active hours"
        if seconds_since_last_send < self.min_seconds_between_sends:
            return False, (
                f"pacing: only {seconds_since_last_send:.0f}s since last send "
                f"(min {self.min_seconds_between_sends:.0f}s)"
            )
        if messages_in_thread >= self.max_messages_per_thread:
            return False, f"thread cap reached ({self.max_messages_per_thread})"
        return True, "ok"
