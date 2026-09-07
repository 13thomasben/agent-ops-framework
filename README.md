# agent-ops-framework

An operating framework for **unattended LLM agents that write into real business systems**: the contracts that decide whether an agent may write at all, the watchdogs that notice when a run never happened, the harnesses that keep a browser agent inside hard caps, and two complete services built the same way.

Everything here is lifted from a private production repo that runs a fleet of ~21 Claude Code agents on scheduled routines for a B2B software company. Those agents read call transcripts, HubSpot, Jira, Slack, and Outlook every day and write coaching reports, CRM notes, tickets, Confluence pages, and Slack posts. Company names, people, IDs, and all per-run data have been replaced with fictional stand-ins ("Acme", `U_EXAMPLE`, `PROJ-123`); the rules, code, and mechanics are unchanged.

Built by [Riley Thomas](https://www.linkedin.com/in/brileyt/) with Claude Code and the Anthropic API, July to September 2026.

## The pattern in one paragraph

A **skill** is a `SKILL.md` that tells a fresh Claude Code session exactly what to do, unattended. A **routine** fires that skill on a cron schedule with a thin entry prompt and a set of env vars. The skill clones this repo, does its job against live systems, writes its state (ledgers, thread logs, proposals) as CSV and JSONL back into the repo, and opens a PR. **Git is the state layer and the audit log.** A handful of **shared contracts** outrank any individual skill and decide how an agent posts, what it may write, and what it does when a human replies. Two **watchdogs** run as skills themselves: one detects runs that did not happen, the other audits the fleet's own repo hygiene. Every new skill ships through the same checklist (`PROCESS.md`) and carries a plain-language canvas for the people who read its output; CI warns when the two drift.

```
 cron routine ──► thin prompt ──► SKILL.md ──► live systems (Slack, HubSpot, Jira, M365)
                                     │                 ▲
                                     │   contracts/ ───┘  (may I write? how? what if someone replies?)
                                     ▼
                              state/*.csv|jsonl ──► commit ──► PR ──► merge
                                     ▲
                 run-health ─────────┘  (did every routine actually fire?)
                 fleet-integrity ────┘  (are state PRs piling up? is the repo self-consistent?)
```

## What is here

| Path | What it is |
|---|---|
| [`contracts/`](contracts/) | The four shared contracts every agent obeys. Start with **[`write-surfaces.md`](contracts/write-surfaces.md)**: the four-axis gate (reversibility, record ownership, audience, attribution) an agent must pass before it writes anywhere, born from an incident where an automation wrote 30 comments onto 24 customer-facing tickets over four weeks. Then [`thread-feedback.md`](contracts/thread-feedback.md) (what an agent does when a human replies: four categories, a blast-radius ladder, propose/approve for CRM edits), [`slack-dispatch.md`](contracts/slack-dispatch.md) (post as the bot, never as a person; labeled fallback), and [`slack-format.md`](contracts/slack-format.md) (message anatomy, emphasis budget, length ceilings, a twelve-check preflight). |
| [`PROCESS.md`](PROCESS.md) | The checklist for shipping a new skill: naming, frontmatter, secrets as env vars, the write gate, the canvas, wiring the routine, fail-soft setup, manual test. |
| [`CLAUDE.md`](CLAUDE.md) | Standing rules a session reads first. "Silence is a valid output." "A number carries its denominator and window, or the reason there is no number." |
| [`skills/run-health/`](skills/run-health/) | Watchdog that detects scheduled runs that **did not happen**, using three independent evidence signals per skill, and escalates after repeated misses. Reports absence, never a guessed cause. |
| [`skills/fleet-integrity-check/`](skills/fleet-integrity-check/) | Weekday audit of unmerged state PRs and repo self-consistency across the fleet. Report-only. |
| [`skills/slack-thread-hygiene/`](skills/slack-thread-hygiene/) | Daily sweep that nudges people who reply out of thread; derives its window from its own last digest so it never double-counts. |
| [`harnesses/webagent/`](harnesses/webagent/) | A Claude-driven Playwright browser agent with step, wall-clock, and cost caps, a domain allowlist, secrets that never enter model context, and an honesty-first `task_failed` path. 39-check offline suite runs the real loop against a fixture site with a scripted model. |
| [`services/daily-brief/`](services/daily-brief/) | FastAPI + Postgres + n8n + Docker service: pulls Microsoft Graph, Slack, and Jira, classifies each person's open loops with an LLM, scores them, and renders a 6:15 AM email that persists items until a real response lands. Reply-to-close via webhook. 25 tests. |
| [`pipelines/marketplace-scout/`](pipelines/marketplace-scout/) | "LLM proposes, code decides." Scores marketplace listings with pydantic structured outputs, then hard-coded guardrails hold every money action for a human via Telegram approval cards. Nine-state sqlite state machine. 50 tests. |
| [`prompts/`](prompts/) | Two example thin entry prompts a routine points at. |
| [`docs/agent-canvases/`](docs/agent-canvases/) | Conventions for the reader-facing channel canvases, plus the manifest CI checks against. |
| [`tracker/`](tracker/) | The AI-ops inventory format (one row per agent, routine, or vendor pilot) with CSV editing rules for multiple Claude accounts sharing one file. |
| [`.github/workflows/canvas-drift.yml`](.github/workflows/canvas-drift.yml) | CI that warns when a skill changes without its canvas. Non-blocking by design. |

## Things that only became rules after they went wrong

- **Post as the bot, never as a person.** The connector's `send_message` writes as whichever human authorized it. One misattributed post is enough.
- **Every write passes the four-axis gate.** A comment on a customer-visible ticket is irreversible, owned by someone else, read by outsiders, and attributed to the company. That combination is a hard no, and it took an incident to write it down.
- **A quiet evening is unknown, not healthy.** Runs can park on a connector approval prompt and never fire. `run-health` reports what did not happen, from evidence, and never guesses why.
- **State goes through PRs, and PRs pile up.** Per-run state commits on `claude/*` branches are safe but accumulate; `fleet-integrity-check` exists because 16 open state PRs across eight skills were invisible until someone counted.
- **Silence is a valid output.** A skill that finds nothing posts nothing. Inventing an all-clear is worse than saying nothing.

## Running the code

```bash
# webagent offline suite: real agent loop, real Chromium, scripted model, no API key
pip install -r harnesses/webagent/requirements.txt && python -m playwright install chromium
python harnesses/webagent/tests/test_offline.py

# marketplace-scout: 50 hermetic tests
cd pipelines/marketplace-scout && pip install -e . && pytest -q

# daily-brief: 21 unit tests run anywhere; 4 more need a local Postgres (see its README)
cd services/daily-brief && pip install -r requirements.txt && pytest -q
```

The skills themselves run inside Claude Code. `PROCESS.md` describes how a routine is wired to one; `.mcp.json.example` lists the connectors they expect.

## What is deliberately not here

The business skills (call intelligence, rep coaching, inbound lead triage, pre-call primers, market intelligence, scorecards) are dense with the company's people, customers, and rules and stay private. Their shape is visible in `tracker/inventory.example.csv` and `skills/run-health/config.example.yaml`. No per-run data, state ledgers, transcripts, or contact lists were copied.

## License

MIT. `pipelines/marketplace-scout` depends on a separately installed AGPL scraper, which is not vendored here.
