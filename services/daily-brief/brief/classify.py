"""Checklist item 5 — the ask classifier. One model call per candidate,
strict JSON via a forced tool call, drop below min confidence rather than
guess. Runs on the company-issued Anthropic key (Commercial Terms)."""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import anthropic

from . import config
from .models import Candidate, Classification

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "ask_classifier.md"

TOOL = {
    "name": "record_classification",
    "description": "Record the classification for this candidate message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_ask": {"type": "boolean"},
            "ask_summary": {"type": "string",
                            "description": "Under 20 words. Factual, no advice, names the counterparty and the ask."},
            "counterparty_class": {"type": "string",
                                   "enum": ["customer", "lender", "oem", "internal", "vendor", "unknown"]},
            "deadline": {"type": ["string", "null"],
                         "description": "YYYY-MM-DD or null. Only if stated or unambiguous."},
            "is_blocking": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["is_ask", "ask_summary", "counterparty_class",
                     "deadline", "is_blocking", "confidence"],
    },
}

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env
    return _client


def _system() -> str:
    return PROMPT_PATH.read_text()


def classify(cand: Candidate) -> Classification | None:
    """Returns None when the candidate should be DROPPED (not an ask, or below
    the confidence floor). Every drop is counted by the caller for the run log."""
    block_direction = {
        "A": "INBOUND EMAIL to the recipient",
        "B": "INBOUND SLACK message to the recipient",
        "D": "OUTBOUND message the recipient SENT (classify the ask they made of the counterparty)",
    }[cand.block]

    user_msg = (
        f"Today: {date.today().isoformat()}\n"
        f"Direction: {block_direction}\n"
        f"Recipient (brief owner): {cand.user_email}\n"
        f"Counterparty: {cand.counterparty or 'unknown'}\n"
        f"Message:\n{cand.text}\n\n"
        f"Thread tail (newest last): {cand.thread_tail or '(none)'}"
    )

    resp = _get_client().messages.create(
        model=os.environ.get("CLASSIFIER_MODEL", "claude-haiku-4-5"),
        max_tokens=300,
        system=_system(),
        messages=[{"role": "user", "content": user_msg}],
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_classification"},
        temperature=0,
    )
    data = next(b.input for b in resp.content if b.type == "tool_use")

    min_conf = config.weights()["brief"]["min_confidence"]
    if not data["is_ask"] or float(data["confidence"]) < min_conf:
        return None

    deadline = None
    if data.get("deadline"):
        try:
            deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
        except ValueError:
            deadline = None
    return Classification(
        is_ask=True,
        ask_summary=" ".join(str(data["ask_summary"]).split())[:200],
        counterparty_class=data["counterparty_class"],
        deadline=deadline,
        is_blocking=bool(data["is_blocking"]),
        confidence=float(data["confidence"]),
    )
