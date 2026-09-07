"""Distance math for the gettability gate — in code, not in the prompt.

Listing locations on FB are text ("Silver Spring, MD"). Resolution order:
1. DMV gazetteer below (instant, offline, covers ~95% of DC-area strings)
2. geopy/Nominatim (lazy import, 1 req/s etiquette, JSON-file cache)
3. None → the pipeline treats distance as unknown (mover-math + a flag),
   never as "close".

Set the home anchor via env SCOUT_HOME_ANCHOR: either "lat,lon" or a
place name resolvable by 1/2 (e.g. a ZIP code via Nominatim, "petworth" via
gazetteer). Until OWNER sets it, the anchor is downtown DC and verdicts carry
an 'anchor_default' caveat.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Optional

DC_CENTER = (38.9072, -77.0369)

# name → (lat, lon). Lowercase keys; matched as substrings of the listing text.
GAZETTEER: dict[str, tuple[float, float]] = {
    "washington": DC_CENTER, "georgetown": (38.9096, -77.0654),
    "capitol hill": (38.8866, -76.9962), "columbia heights": (38.9296, -77.0286),
    "petworth": (38.9367, -77.0261), "navy yard": (38.8762, -77.0004),
    "anacostia": (38.8625, -76.9846), "brookland": (38.9418, -76.9894),
    "arlington": (38.8816, -77.0910), "alexandria": (38.8048, -77.0469),
    "falls church": (38.8823, -77.1711), "annandale": (38.8304, -77.1964),
    "springfield": (38.7893, -77.1872), "fairfax": (38.8462, -77.3064),
    "vienna": (38.9012, -77.2653), "mclean": (38.9339, -77.1773),
    "reston": (38.9586, -77.3570), "herndon": (38.9696, -77.3861),
    "burke": (38.7935, -77.2717), "lorton": (38.7043, -77.2278),
    "woodbridge": (38.6582, -77.2497), "manassas": (38.7509, -77.4753),
    "ashburn": (39.0438, -77.4874), "sterling": (39.0062, -77.4286),
    "leesburg": (39.1157, -77.5636), "centreville": (38.8404, -77.4289),
    "chantilly": (38.8943, -77.4311), "bethesda": (38.9847, -77.0947),
    "chevy chase": (38.9807, -77.0781), "silver spring": (38.9907, -77.0261),
    "takoma park": (38.9779, -77.0075), "rockville": (39.0840, -77.1528),
    "gaithersburg": (39.1434, -77.2014), "germantown": (39.1732, -77.2717),
    "wheaton": (39.0398, -77.0553), "college park": (38.9807, -76.9369),
    "hyattsville": (38.9559, -76.9455), "greenbelt": (39.0046, -76.8755),
    "laurel": (39.0993, -76.8483), "bowie": (38.9426, -76.7302),
    "upper marlboro": (38.8157, -76.7497), "waldorf": (38.6246, -76.9391),
    "clinton": (38.7651, -76.8983), "fort washington": (38.7073, -77.0233),
    "columbia": (39.2037, -76.8610), "ellicott city": (39.2673, -76.7983),
    "baltimore": (39.2904, -76.6122), "annapolis": (38.9784, -76.4922),
    "frederick": (39.4143, -77.4105), "fredericksburg": (38.3032, -77.4605),
    "stafford": (38.4221, -77.4083), "dumfries": (38.5676, -77.3280),
}


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(h))


class Geo:
    def __init__(self, anchor: Optional[str] = None,
                 cache_path: Path = Path.home() / ".scout-geocache.json"):
        self._cache_path = cache_path
        self._cache: dict[str, Optional[list[float]]] = {}
        if cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text())
            except Exception:
                self._cache = {}
        raw = anchor if anchor is not None else os.environ.get("SCOUT_HOME_ANCHOR", "")
        self.anchor, self.anchor_default = self._resolve_anchor(raw)

    def _resolve_anchor(self, raw: str) -> tuple[tuple[float, float], bool]:
        raw = raw.strip()
        if not raw:
            return DC_CENTER, True
        m = re.fullmatch(r"(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)", raw)
        if m:
            return (float(m.group(1)), float(m.group(2))), False
        pt = self.locate(raw)
        return (pt, False) if pt else (DC_CENTER, True)

    def locate(self, location_text: str) -> Optional[tuple[float, float]]:
        """Resolve free-text location → (lat, lon) or None."""
        text = location_text.strip().lower()
        if not text:
            return None
        for name, point in GAZETTEER.items():
            if name in text:
                return point
        if text in self._cache:
            hit = self._cache[text]
            return (hit[0], hit[1]) if hit else None
        point = self._nominatim(text)
        self._cache[text] = list(point) if point else None
        try:
            self._cache_path.write_text(json.dumps(self._cache))
        except Exception:
            pass
        return point

    def _nominatim(self, text: str) -> Optional[tuple[float, float]]:  # pragma: no cover
        try:
            from geopy.geocoders import Nominatim  # lazy — optional dependency
            loc = Nominatim(user_agent="marketplace-scout-personal", timeout=8).geocode(
                f"{text}, USA")
            return (loc.latitude, loc.longitude) if loc else None
        except Exception:
            return None

    def miles_from_home(self, location_text: str) -> Optional[float]:
        point = self.locate(location_text)
        return round(haversine_miles(self.anchor, point), 1) if point else None
