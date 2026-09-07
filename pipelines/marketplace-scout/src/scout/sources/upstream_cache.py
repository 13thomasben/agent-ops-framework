"""Sidecar source: read listings the upstream monitor has already scouted.

Why sidecar instead of forking upstream (decided Jul 2026): upstream keeps
doing what it's good at — human-paced Facebook search on a real logged-in
browser, plus caching every listing's details in diskcache at
~/.ai-marketplace-monitor (key = ("listing-details", post_url), value = the
Listing dataclass as a dict: id, title, image, price, post_url, location,
seller, condition, description, name). We read that cache read-only; upstream
never notifies (scout mode: no [ai.*] sections, no notification channels in
its config) and our brain owns all judging + Telegram traffic. Zero fork
drift, zero duplicate scraping, one browser touching Facebook.

Known limitation: upstream caches ONE primary photo per listing. Good enough
for Phase 1 scoring; the Phase 2 Messenger driver owns the browser session and
will pull full galleries when a listing graduates to negotiation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from ..schema import Listing

DEFAULT_CACHE_DIR = Path.home() / ".ai-marketplace-monitor"
LISTING_TAG = "listing-details"  # upstream utils.CacheType.LISTING_DETAILS.value


def parse_price(raw: object) -> float:
    """Upstream stores price as text ('$1,234', 'CA$50', 'Free')."""
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw or "")
    m = re.search(r"(\d[\d,]*\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else 0.0


def from_upstream_dict(d: dict) -> Listing:
    """Map upstream's cached Listing dict → our Listing model."""
    image = d.get("image") or ""
    return Listing(
        id=str(d.get("id") or d.get("post_url", "")),
        url=str(d.get("post_url", "")),
        title=str(d.get("title", "")),
        price=parse_price(d.get("price")),
        description=str(d.get("description", "")),
        photos=[image] if image else [],
        location=str(d.get("location", "")),
        seller_name=str(d.get("seller", "")),
        condition=str(d.get("condition", "")),
        want_slug=str(d.get("name", "")),   # upstream stores the [item.X] name
    )


def iter_cached_listings(cache_dir: Path = DEFAULT_CACHE_DIR) -> Iterator[Listing]:
    """Yield every cached listing. Lazy diskcache import keeps tests hermetic."""
    from diskcache import Cache  # lazy — runtime dependency only

    cache = Cache(str(cache_dir))
    try:
        for key in cache.iterkeys():
            if not (isinstance(key, tuple) and len(key) == 2 and key[0] == LISTING_TAG):
                continue
            value = cache.get(key)
            if isinstance(value, dict) and value.get("post_url"):
                try:
                    yield from_upstream_dict(value)
                except Exception:
                    continue  # one malformed entry must never kill the loop
    finally:
        cache.close()
