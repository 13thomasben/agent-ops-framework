# marketplace-scout

Watches Facebook Marketplace (DC), scores deals the minute they post, negotiates within hard guardrails, and preps one-tap Venmo payment + Lugg pickup. Design goal: **two taps per purchase**, neither of which is time-sensitive, because a mover goes instead of you.

> **Status: personal project.** This is a sanitized public showcase copy. Phase 0 and Phase 1 are real and tested; Phase 2 (negotiator) is a stub with an interface contract, and Phase 3 (closing) is partial — payment prefill links and the mover cost math are real, the booking flow is a stub. Personal identifiers, budgets, and the owner's private planning doc have been replaced with placeholders or omitted.

**Read `CLAUDE.md` first** — it's the working brief (architecture, locked decisions, hard rules, phase criteria). The full plan with research and sources lives in `docs/plan.md` in the private repo; it is personal planning and is not included here.

## Status

Phase 0 is runnable today (config below). Phases 1–3 are scaffolded: the deterministic core (guardrails, offer playbook, state machine, payment links, Lugg cost math) is real and tested; the Facebook/Messenger/Telegram wiring is stubbed with interface contracts.

## Phase 0 quickstart (the radar — no code required)

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install ai-marketplace-monitor
playwright install
mkdir $env:USERPROFILE\.ai-marketplace-monitor
copy configs\example.toml $env:USERPROFILE\.ai-marketplace-monitor\config.toml
# edit that file: search_city location ID, Anthropic API key, Telegram token/chat id
ai-marketplace-monitor
```

A browser window opens — log into Facebook once (solve any captcha yourself), then leave it running. Scored alerts arrive on Telegram 30–60 min after listings post.

## Developing (Phases 1–3)

```powershell
pip install -e ".[dev]"
pytest -q
```

Repo map:

```
CLAUDE.md                     the brief — read first, keep truthful
configs/example.toml          Phase 0 config (example: a used desk hunt)
configs/upstream-scout.toml   Phase 1 scout-mode config for the upstream monitor
configs/wants/                one TOML per want (example: desk.toml)
docs/phase1-design.md         Phase 1 architecture (sidecar, not fork)
docs/plan.md                  full build plan + research sources — OMITTED from this public copy
src/scout/
  schema.py                   DealVerdict, ListingState, Listing (pydantic)
  guardrails.py               hard caps: hours, message rates, price ceilings  [real, tested]
  payments.py                 Venmo/CashApp prefill links — the ONLY payment code allowed  [real, tested]
  state.py                    sqlite listing state machine  [real, tested]
  scoring/brain.py            Phase 1: listing → DealVerdict via Anthropic API  [skeleton]
  negotiation/playbook.py     deterministic offer ladder — the model never picks prices  [real, tested]
  negotiation/messenger.py    Phase 2: Playwright Messenger driver  [stub + contract]
  closing/lugg.py             Lugg cost estimate [real, tested] + booking prefill [stub]
  approvals/telegram_bot.py   Phase 1: the approval card + buttons  [skeleton]
tests/                        hermetic — no network, no keys, no Facebook
```

Naming note: in this public copy the Python package and CLI are called `scout` (`scout run`, `scout want add`, …). In the architecture docs, "SCOUT" also names the *upstream* monitor stage that touches Facebook; the sidecar package reads that scout's cache. Context makes it clear which is meant.

## Notes

- Runs on OWNER's laptop only: headed browser, real profile, home IP. Never cloud, never headless. See CLAUDE.md hard rules.
- Upstream scout: [ai-marketplace-monitor](https://github.com/BoPeng/ai-marketplace-monitor) (AGPL-3.0) via pip — a separately installed package, not vendored; licensing notes in CLAUDE.md.
- Private personal project; no license granted for redistribution (revisit if productizing).
