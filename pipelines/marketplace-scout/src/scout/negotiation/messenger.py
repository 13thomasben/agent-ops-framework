"""Phase 2 STUB — Messenger driver over the same logged-in Playwright session.

Contract for the implementation (do not widen it):

- Reuses the upstream monitor's authenticated browser context; never opens a
  second login. Headed only.
- Every outbound send passes Guardrails.allow_send() and, for the first message
  of a thread, Guardrails.allow_new_conversation(). Denials are logged and the
  message is queued, not forced.
- Warm-up mode (`draft=True`): outbound messages go to the Telegram approval
  card instead of Facebook; OWNER's tap flips draft -> sent.
- Typing is simulated at human speed (upstream types at ~250ms/char for login;
  match that ballpark) with jittered pauses before send.
- Reads are polled alongside the normal monitor cycle — no tight refresh loop.
- Anything unexpected in a thread (calls requested, links, payment weirdness,
  price we can't parse) -> return it for ESCALATE; never improvise.

Ban-risk note (docs/plan.md blocker #2): message *sending* is the most
detectable thing this project does. Keep volumes tiny; the caps in
guardrails.py are not tuning knobs.
"""

from __future__ import annotations

from ..schema import ThreadMessage


class MessengerDriver:
    """Interface only — Phase 2 implements against the live Playwright page."""

    def open_thread(self, listing_url: str) -> str:
        """Open (or create) the buyer->seller thread; return a thread id."""
        raise NotImplementedError("Phase 2")

    def read_new(self, thread_id: str) -> list[ThreadMessage]:
        """Return messages newer than the last read cursor."""
        raise NotImplementedError("Phase 2")

    def send(self, thread_id: str, text: str, *, draft: bool) -> ThreadMessage:
        """Send (or queue as draft in warm-up mode). Callers MUST have passed
        Guardrails checks before calling; this method re-checks and refuses
        anyway — belt and suspenders."""
        raise NotImplementedError("Phase 2")
