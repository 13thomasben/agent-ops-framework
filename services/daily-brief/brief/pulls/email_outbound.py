"""Block D (email half) — mail the user sent that contained an ask and never
got a reply (spec §2, 21-day lookback). This is the block that makes the brief
something people want: their own follow-up list."""
from __future__ import annotations

from ..models import Candidate, counts_as_words
from . import filtering, graph


def pull(user: dict, snapshot: graph.MailboxSnapshot, cap: int = 30) -> list[Candidate]:
    ue = user["email"].lower()
    out: list[Candidate] = []

    for conv_id, msgs in snapshot.by_conversation().items():
        last = msgs[-1]
        if graph.addr(last.get("from")) != ue:
            continue  # thread's last word isn't the user's → nobody owes them here
        if not counts_as_words(last.get("bodyPreview")):
            continue
        recipients = [r for r in (graph.addr(x) for x in last.get("toRecipients", []))
                      if r and r != ue]
        if not recipients:
            continue
        # waiting on a robot is not an open loop
        if all(filtering.is_noise_email(r, "") for r in recipients):
            continue
        if any(filtering.do_not_ingest_email(r) for r in recipients):
            continue

        body = graph.get_body_text(snapshot.upn, last["id"]) or last.get("bodyPreview", "")
        counterparty = graph.name_and_addr(last.get("toRecipients", [{}])[0])
        out.append(Candidate(
            user_email=user["email"], block="D", source="email",
            source_id=f"{conv_id}#d",           # distinct row from any Block A item on the thread
            permalink=last.get("webLink"),
            counterparty=counterparty,
            text=f"Subject: {last.get('subject','')}\n\n{body[:2500]}",
            asked_at=graph.ts(last),
        ))

    out.sort(key=lambda c: c.asked_at, reverse=True)
    return out[:cap]
