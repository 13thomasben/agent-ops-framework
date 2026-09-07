"""Block A — inbound email awaiting the user's reply (spec §2, 21-day lookback).

Kept: mail addressed to the user personally where the newest counterparty
message has no later reply from the user AND no later substantive reply from
anyone else. Everything kept here still has to convince the ask classifier."""
from __future__ import annotations

from ..models import Candidate, counts_as_words
from . import filtering, graph


def pull(user: dict, snapshot: graph.MailboxSnapshot, cap: int = 30) -> list[Candidate]:
    ue = user["email"].lower()
    out: list[Candidate] = []

    for conv_id, msgs in snapshot.by_conversation().items():
        inbound = [m for m in msgs
                   if graph.addr(m.get("from")) not in ("", ue)
                   and m.get("receivedDateTime")]
        if not inbound:
            continue

        ask = inbound[-1]  # newest counterparty message on the thread
        sender = graph.addr(ask.get("from"))

        if filtering.do_not_ingest_email(sender):
            continue
        if graph.is_calendar_message(ask) or filtering.is_noise_email(sender, ask.get("subject", "")):
            continue
        to_addrs = [graph.addr(r) for r in ask.get("toRecipients", [])]
        if not filtering.personally_addressed(ue, to_addrs):
            continue  # group alias / CC-only — anyone could answer

        after_ask = [m for m in msgs if graph.ts(m) > graph.ts(ask)]
        if any(graph.addr(m.get("from")) == ue for m in after_ask):
            continue  # the user already replied (closure pass handles the state row)
        if any(graph.addr(m.get("from")) not in (ue, sender)
               and counts_as_words(m.get("bodyPreview")) for m in after_ask):
            continue  # someone else already answered (spec exclusion)

        body = graph.get_body_text(snapshot.upn, ask["id"]) or ask.get("bodyPreview", "")
        tail = " | ".join(f"{graph.name_and_addr(m.get('from'))}: {m.get('bodyPreview','')[:120]}"
                          for m in msgs[-3:])
        out.append(Candidate(
            user_email=user["email"], block="A", source="email", source_id=conv_id,
            permalink=ask.get("webLink"),
            counterparty=graph.name_and_addr(ask.get("from")),
            text=f"Subject: {ask.get('subject','')}\n\n{body[:2500]}",
            asked_at=graph.ts(ask), thread_tail=tail,
        ))

    out.sort(key=lambda c: c.asked_at, reverse=True)
    return out[:cap]
