"""Phase 1 deal brain — listing + photos + a Want → DealVerdict.

Soft-fit philosophy (OWNER, Jul 2026): the Want's brief describes INTENT
("around 60in long, 30-35in tall, tasteful wood, sturdy"). There are no rigid
dimension gates — the model judges like a sharp human buyer whether a piece
serves the same purpose, and says why in fit_notes. Code owns what code should
own: distance (geo.py), delivery cost (transport.py), the value gate
(pipeline.py), and rate limits. The model owns judgment; it never owns math
that moves money.

Runtime calls the Anthropic API directly (this is a service, not a Claude Code
session). Photos: upstream caches one primary image per listing — fetched
locally and sent as base64 (FB CDN URLs are signed and expire, so we fetch
immediately). Verdicts should be cached by (listing id, price) by the caller;
the pipeline handles that via the state store.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Optional

from ..schema import DealVerdict, Listing, Want

MODEL = "claude-sonnet-5"  # keep in sync with the scout config note; retired
                           # model ids 404 — pin explicitly, never rely on defaults.

SCORING_PROMPT = """\
You are a ruthless personal buying scout for secondhand marketplaces in the
Washington, DC area. You evaluate ONE listing against ONE "want" and return
strict JSON. Judge like a sharp human buyer: the want describes intent, not
rigid specs — reason about whether this piece genuinely serves that intent
(e.g. a target of "around 60 inches" tolerates 52-66; a nightstand does not
become a dresser). Photos outrank text when they disagree.

THE WANT:
{brief}

THE LISTING:
Title: {title}
Asking price: ${price}
Condition field: {condition}
Location text: {location}
Description:
{description}

LOGISTICS CONTEXT (computed, trust these numbers):
- Distance from home: {distance}
- Delivery cost if it fits in a sedan (courier): ${sedan}
- Delivery cost if bulky one-person (SUV/pickup): ${suv}
- Delivery cost if it needs two movers: ${two_person}
- Value bar: notify only if (price + delivery) <= {value_bar} x fair resale value
{budget_line}

Rules:
- transport_class: judge from photos/text what it takes to move this item.
  "sedan" = fits in a car under ~30 lb; "suv" = bulky one-person; "two_person"
  = real furniture. When unsure between two, pick the bigger.
- fair_value: realistic local secondhand resale for the condition SHOWN, not
  hopeful retail. Note brand evidence in fit_notes when photos show it.
- Be ruthless: a notification interrupts a human's day. Merely fair deals are
  notify=false. Flag scam signals (stock photos, absurd price, vague seller).
- missing_info: the 1-3 things a buyer should ask the seller before paying.
- opening_offer / max_price: what a disciplined buyer would open at and walk
  away above, given fair_value and the delivery cost for your transport_class.

Respond with ONLY a JSON object, no prose, exactly:
{{
  "fit": <0-10 int>,
  "fit_notes": "<2-3 sentences: does this serve the want's intent, incl. dimension reasoning>",
  "quality": <0-10 int>,
  "transport_class": "sedan" | "suv" | "two_person",
  "fair_value": <USD number>,
  "max_price": <USD number>,
  "opening_offer": <USD number>,
  "scam_flags": [<strings, empty if clean>],
  "dimensions_confirmed": <true|false>,
  "missing_info": [<strings>],
  "notify": <true|false>,
  "summary": "<2 sentences: verdict and why>"
}}
"""


def build_prompt(listing: Listing, want: Want, *, distance_miles: Optional[float],
                 cost_menu: dict[str, float]) -> str:
    distance = (f"{distance_miles} miles" if distance_miles is not None
                else f"UNKNOWN (location text was: {listing.location!r} — never assume close)")
    budget_line = (f"- Hard budget hint: all-in above ${want.max_budget:.0f} is very unlikely to be approved."
                   if want.max_budget else "")
    return SCORING_PROMPT.format(
        brief=want.brief.strip(),
        title=listing.title,
        price=f"{listing.price:.0f}",
        condition=listing.condition or "not stated",
        location=listing.location or "not stated",
        description=(listing.description or "(none)")[:4000],
        distance=distance,
        sedan=f"{cost_menu.get('sedan', 25):.0f}",
        suv=f"{cost_menu.get('suv', 45):.0f}",
        two_person=f"{cost_menu.get('two_person', 115):.0f}",
        value_bar=f"{want.value_bar:.2f}",
        budget_line=budget_line,
    )


def fetch_photo_blocks(urls: list[str], max_photos: int = 4,
                       max_bytes: int = 4_500_000) -> list[dict]:
    """Download listing photos → Anthropic image blocks. Failures are skipped:
    a missing photo degrades the verdict, it must never block scoring."""
    blocks: list[dict] = []
    if not urls:
        return blocks
    try:
        import httpx  # lazy
    except ModuleNotFoundError:  # pragma: no cover
        return blocks
    for url in urls[:max_photos]:
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            data = resp.content
            if not data or len(data) > max_bytes:
                continue
            media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
            if not media_type.startswith("image/"):
                continue
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type,
                           "data": base64.standard_b64encode(data).decode()},
            })
        except Exception:
            continue
    return blocks


def score_listing(listing: Listing, want: Want, *,
                  distance_miles: Optional[float],
                  cost_menu: dict[str, float],
                  client=None, model: str = MODEL) -> DealVerdict:
    """Score one listing against one want. Inject `client` in tests."""
    if client is None:  # pragma: no cover - live path
        import anthropic

        client = anthropic.Anthropic()
    prompt = build_prompt(listing, want, distance_miles=distance_miles,
                          cost_menu=cost_menu)
    content: list[dict] = fetch_photo_blocks(listing.photos)
    content.append({"type": "text", "text": prompt})
    response = client.messages.create(
        model=model,
        max_tokens=900,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(block.text for block in response.content if hasattr(block, "text"))
    verdict = parse_verdict(text)
    verdict.distance_miles = distance_miles
    return verdict


def parse_verdict(text: str) -> DealVerdict:
    """Tolerant JSON extraction (models occasionally wrap output in fences)."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", candidate).strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return DealVerdict.model_validate(json.loads(candidate[start:end + 1]))


# ---------------------------------------------------------------------------
# Want compiler: OWNER types an idea → search phrases + price band + brief.
# ---------------------------------------------------------------------------

COMPILE_PROMPT = """\
Turn this rough idea of something to buy on Facebook Marketplace into search
configuration. Respond with ONLY JSON, exactly:
{{
  "slug": "<short_snake_case_name>",
  "search_phrases": [<3-5 short marketplace search strings people actually list under>],
  "min_price": <int USD, set to skip the junk/scam tier for this item type>,
  "max_price": <int USD, generous ceiling so good overpriced-then-negotiable finds still appear>,
  "antikeywords": [<0-5 words that exclude common false positives>],
  "brief": "<the idea rewritten as a clear buyer's brief: intent, target size/specs as SOFT targets with sensible tolerances, materials/style preferences, quality signals to prefer and avoid. Keep every fact the human stated; do not invent constraints they did not imply.>"
}}

THE IDEA: {idea}
"""


def compile_want(idea: str, client=None, model: str = MODEL) -> dict:
    """Idea text → dict for Want + upstream item section. Inject client in tests."""
    if client is None:  # pragma: no cover - live path
        import anthropic

        client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=700,
        messages=[{"role": "user", "content": COMPILE_PROMPT.format(idea=idea)}],
    )
    text = "".join(block.text for block in response.content if hasattr(block, "text"))
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", candidate).strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    return json.loads(candidate[start:end + 1])
