"""Core shapes. The stable item ID is the persistence anchor: the same open
loop must hash to the same row every single day, or there is no day counter
and no accountability."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime


def stable_id(user_email: str, source: str, source_id: str) -> str:
    """Deterministic 16-hex ID. Inputs are normalized so cosmetic differences
    (case, whitespace) can never fork an item into a new row."""
    key = "|".join(s.strip().lower() for s in (user_email, source, source_id))
    return hashlib.sha256(key.encode()).hexdigest()[:16]


_SHORTCODE = re.compile(r":[a-z0-9_+\-]+:")          # :thumbsup: :eyes: :white_check_mark:
_MENTION_OR_MARKUP = re.compile(r"<[^>]{1,40}>")     # <@U123>, <!here>, <#C123|chan>


def counts_as_words(text: str | None, min_letters: int = 5) -> bool:
    """THE emoji rule, in one function. A response counts only if it contains
    actual words — at least `min_letters` alphabetic characters after stripping
    emoji (unicode and :shortcode: form), Slack markup, punctuation, digits,
    and whitespace. '👍', '✅✅', ':thumbsup:', '<@U123> 👀', and empty bodies
    all fail. 'ok will do' passes."""
    if not text:
        return False
    cleaned = _SHORTCODE.sub("", text.lower())
    cleaned = _MENTION_OR_MARKUP.sub("", cleaned)
    letters = "".join(c for c in cleaned if c.isalpha())
    return len(letters) >= min_letters


@dataclass
class Candidate:
    """A pre-classifier candidate from one of the four pulls."""
    user_email: str
    block: str                 # A | B | C | D
    source: str                # email | slack | jira
    source_id: str
    permalink: str | None
    counterparty: str | None   # display name or address of the other side
    text: str                  # what the classifier reads (subject + body / message / summary)
    asked_at: datetime | None  # when the (latest) ask landed
    thread_tail: str = ""      # last few thread messages, for context
    meta: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return stable_id(self.user_email, self.source, self.source_id)


@dataclass
class Classification:
    """Strict output of the ask classifier (spec §7 item 5)."""
    is_ask: bool
    ask_summary: str           # under 20 words
    counterparty_class: str    # customer|lender|oem|internal|vendor|unknown
    deadline: date | None
    is_blocking: bool
    confidence: float
