"""Listing state machine + sqlite persistence (stdlib only).

One row per listing. The state machine is the cure for "I lose track of
things": every live deal is queryable, and illegal jumps raise instead of
silently corrupting a thread.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .schema import Listing, ListingState

# Legal transitions. DEAD is reachable from anywhere (sold out from under us,
# scam discovered, OWNER kills it). Terminal states: DONE, DEAD.
TRANSITIONS: dict[ListingState, set[ListingState]] = {
    ListingState.SPOTTED: {ListingState.SCORED},
    ListingState.SCORED: {ListingState.PASSED, ListingState.WATCHING, ListingState.INQUIRING},
    ListingState.PASSED: {ListingState.WATCHING},          # price drop can revive
    ListingState.WATCHING: {ListingState.INQUIRING},
    ListingState.INQUIRING: {ListingState.NEGOTIATING},
    ListingState.NEGOTIATING: {ListingState.AGREED},
    ListingState.AGREED: {ListingState.AWAITING_APPROVAL},
    ListingState.AWAITING_APPROVAL: {ListingState.SCHEDULED, ListingState.NEGOTIATING},
    ListingState.SCHEDULED: {ListingState.DONE},
    ListingState.DONE: set(),
    ListingState.DEAD: set(),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    state TEXT NOT NULL,
    verdict_json TEXT,
    thread_json TEXT,
    notes TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processed (
    key TEXT PRIMARY KEY,
    at TEXT NOT NULL
);
"""


class InvalidTransition(RuntimeError):
    pass


class ListingStore:
    """Thin sqlite wrapper. Not thread-safe by design — one monitor process."""

    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ---- writes ------------------------------------------------------------

    def upsert(self, listing: Listing, state: ListingState = ListingState.SPOTTED) -> None:
        self._conn.execute(
            """INSERT INTO listings (id, url, title, price, state, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at""",
            (listing.id, listing.url, listing.title, listing.price, state.value, _now()),
        )
        self._conn.commit()

    def transition(self, listing_id: str, to: ListingState, note: str = "") -> None:
        current = self.state_of(listing_id)
        if to is not ListingState.DEAD and to not in TRANSITIONS[current]:
            raise InvalidTransition(f"{listing_id}: {current.value} -> {to.value} is not legal")
        self._conn.execute(
            "UPDATE listings SET state=?, notes=notes || ?, updated_at=? WHERE id=?",
            (to.value, f"\n[{_now()}] -> {to.value}: {note}" if note else f"\n[{_now()}] -> {to.value}",
             _now(), listing_id),
        )
        self._conn.commit()

    def attach_verdict(self, listing_id: str, verdict_json: str) -> None:
        self._conn.execute(
            "UPDATE listings SET verdict_json=?, updated_at=? WHERE id=?",
            (verdict_json, _now(), listing_id),
        )
        self._conn.commit()

    def attach_thread(self, listing_id: str, messages: Iterable[dict]) -> None:
        self._conn.execute(
            "UPDATE listings SET thread_json=?, updated_at=? WHERE id=?",
            (json.dumps(list(messages)), _now(), listing_id),
        )
        self._conn.commit()

    def mark_processed(self, key: str) -> None:
        """Dedupe key for the pipeline — typically '<listing_id>@<price>' so a
        price drop re-qualifies the same listing for scoring."""
        self._conn.execute(
            "INSERT OR IGNORE INTO processed (key, at) VALUES (?, ?)", (key, _now())
        )
        self._conn.commit()

    def was_processed(self, key: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM processed WHERE key=?", (key,)
        ).fetchone() is not None

    # ---- reads ---------------------------------------------------------------

    def state_of(self, listing_id: str) -> ListingState:
        row = self._conn.execute(
            "SELECT state FROM listings WHERE id=?", (listing_id,)
        ).fetchone()
        if row is None:
            raise KeyError(listing_id)
        return ListingState(row["state"])

    def active(self) -> list[sqlite3.Row]:
        """Everything not terminal — the '/status' view."""
        return self._conn.execute(
            "SELECT * FROM listings WHERE state NOT IN (?, ?, ?) ORDER BY updated_at DESC",
            (ListingState.DONE.value, ListingState.DEAD.value, ListingState.PASSED.value),
        ).fetchall()

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
