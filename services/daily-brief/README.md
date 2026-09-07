# daily-brief — Daily Accountability Brief

> **Status: built and tested locally; not deployed.** All v1 scope is
> implemented and covered by tests (including the emoji rule) and an
> end-to-end fixture demo, but the stand-up runbook was never executed against
> a real box, mailbox, or credentials. This is a sanitized public copy: the
> company, people, customers, and tenant identifiers have been replaced with
> fictional placeholders (`Acme`, `acme.example.com`, `U_EXAMPLE`, `PROJ`).

One email per person each morning listing every open loop they own, and the
loop stays on the list until a **real response** is detected. Built for one
team at one company, delivered from one shared mailbox, to a written v1 build
brief from a sponsor.

Three rules outrank everything else in this codebase:

1. **Emoji is not a response.** A 👍 leaves the item fully open. Closure
   requires words or an observable action. `brief/models.py::counts_as_words`
   is the rule; `brief/pulls/slack.py` cannot even fetch reactions;
   `tests/test_closure.py` proves it.
2. **Persistence is the product.** Every item is one Postgres row for life
   (`db/001_init.sql`). `first_seen` never moves, `days_open` is derived at
   read time, and day 4 reads "open 4 days" with no counter cron. The state
   store was built and tested before any pull logic.
3. **Email only, not Slack.** Delivery is a 6:15am ET HTML email from a
   shared mailbox (`brief@acme.example.com`). Slack is a source, never a
   surface.

## The four blocks (spec §2)

| Block | What | Lookback | Pull |
|---|---|---|---|
| A | Inbound email awaiting your reply | 21d | `brief/pulls/email_inbound.py` |
| B | Inbound Slack awaiting your response | 14d | `brief/pulls/slack_inbound.py` |
| C | Open Jira issues in scoped projects assigned to you (+7-day stale flag) | all | `brief/pulls/jira_assigned.py` |
| D | Your outbound nobody answered | 21d | `email_outbound.py` + `slack_outbound.py` |

## Pipeline (per active user, weekday mornings)

pull → filter (`config/filters.yaml`: do-not-ingest, then noise) → classify
(`prompts/ask_classifier.md`, strict JSON, drop < 0.6) → **upsert state** →
closure sweep (`brief/closure.py`) → tier + score (`brief/score.py`,
weights in `config/weights.yaml`) → select (cap 15 A–C, D uncapped) → render
(`brief/render.py`, mobile-first, every item deep-linked with a day counter) →
send → freeze the printed numbering → log the run (`runs` table).

Replies of "close 4, 7" to the brief close items manually
(`brief/reply_close.py`) and double as labeled data on classifier mistakes.

## Stack

FastAPI service + Postgres 16 + n8n (scheduling, OAuth redirect, error alerts)
+ Caddy (public HTTPS for the n8n webhooks), all in one `docker-compose.yml`.
Sources: Microsoft Graph (mail), Slack Web API (per-user tokens), Jira Cloud
REST. Classifier: Anthropic Messages API with a forced tool call.

## Auth (decided)

Hybrid, see `docs/AUTH.md`: M365 app-only + admin consent (Path A), Slack
per-user OAuth tokens (Path B — forced by platform), Jira service account.
The credential broker (`brief/credentials.py`) isolates the whole question.

## Run it

```bash
cp .env.example .env                        # fill (docs/RUNBOOK.md walks every value)
cp config/roster.example.yaml config/roster.yaml   # fill with real people
docker compose up -d                        # postgres + n8n + service
# import the n8n/*.json workflows, activate → 6:15am ET weekdays

# dev / dry-run:
pip install -r requirements.txt
python -m brief.run --user owner --dry-run  # HTML to out/, no send

# proof with zero credentials:
DATABASE_URL=postgresql:///brief_demo BRIEF_CONFIG_DIR=fixtures/demo-config \
  python scripts/demo_fixture_run.py
pytest                                      # 25 tests, incl. the emoji rule
```

## Rollout (spec §8 — expand on accuracy, not on schedule)

Week 1 sponsor only (owner reviews daily, bar: <2 of 10 wrong) → week 2 add
the team lead → leadership after two clean weeks → team. Onboarding a person =
fill their roster row, add mailbox to the `brief-scope` group, send their Slack
consent link, flip `active: true`. Tuning changes land in
`docs/TUNING-LOG.md`, dated.

## Not in v1 (spec §10 + docs/SCOPE-TRACE.md)

Task-system push, manager roll-up, calendar-aware suppression,
meeting-transcript commitments, calendar-linked "Today" tier. The scope trace
records every deliberate delta from the written brief.
