# CLAUDE.md — Marketplace Scout

An agent that watches Facebook Marketplace (Washington, DC), scores deals instantly, negotiates within hard guardrails, and preps one-tap payment + Lugg pickup so OWNER spends at most **two taps per purchase**. Full plan with research and sources: `docs/plan.md` (omitted from this public copy). First target was a dresser; the shipped example config hunts a used desk.

## Current status (update this section as phases land)

- **Phase 0** (radar via upstream `ai-marketplace-monitor`): **LIVE as of Jul 23, 2026** — v0.10.2 + Playwright Chromium in `.venv` (plus `python-magic-bin`: upstream's pushbullet dep segfaults on Windows without it). Config at `~/.ai-marketplace-monitor/config.toml` (mirror of `configs/example.toml`): `search_city = 'LOCATION_ID'` (numeric Marketplace location ID, search-verified), `model = 'claude-sonnet-5'` (an explicit `model` is **required** — upstream's default `claude-sonnet-4-20250514` was retired and 404s), `login_wait_time = '5m'` (default 60s was too short to catch the login window). Secrets are `${ENV}` refs resolved from User-scope env vars, set via `scripts\setup-secrets.ps1` (masked prompts, live verification, bot-to-phone test). Launch via `scripts\run-radar.ps1`. Known noise: intermittent `[Search] Failed to get search results` per query variant — listings still parse and score; it's the fragile-selector layer, watch but don't panic.
- **Phase 1** (generalized deal brain + sidecar + Telegram buttons): **BUILT Jul 23 in Cowork, awaiting laptop wiring** — any-item wants (configs/wants/), soft-fit photo scoring, code-enforced geo/delivery/value gates, sidecar reads the upstream cache. See docs/phase1-design.md + runbook below. 50 tests green.
- **Phase 2** (negotiator): stubs only — `negotiation/messenger.py`; `negotiation/playbook.py` logic is real and tested.
- **Phase 3** (closing kit + haul): partial — `payments.py` is real, `closing/lugg.py` estimate is real, booking is a stub.
- Tests: `pytest -q` green on payments, guardrails, playbook, state, lugg estimate. Tests never require network, API keys, or Facebook.

## Locked decisions (July 22, 2026 — do not silently revisit)

1. Build order: watch + score → negotiate → close.
2. Negotiation autonomy: warm-up (draft-mode, OWNER taps send) → auto-within-guardrails.
3. Runtime: OWNER's Windows laptop. Headed browser, OWNER's real logged-in profile, home IP.
4. Market: Washington, DC (`search_city` ID read from OWNER's own marketplace URL).
5. **Money and mover bookings are a human tap, permanently.** The bot prepares; OWNER approves.

## Hard rules (enforce in code, not prompts)

- **NEVER automate a payment send.** Venmo/Zelle/CashApp browser automation is forbidden here — it trips fraud models (account freezes ~180 days), sends are irreversible, and no sanctioned API exists. `payments.py` builds prefill links only; `guardrails.require_human_for_money()` is a constant `True`, not a setting.
- **NEVER run against Facebook headless, from a cloud/datacenter IP, or on any account other than OWNER's real one.** These are the top checkpoint/ban triggers (see docs/plan.md, blocker #2).
- All outbound messaging passes `Guardrails` checks: active hours, per-day new-conversation cap, per-thread message cap, minimum spacing between sends. The LLM writes prose *inside* those rails; every price boundary comes from `negotiation/playbook.py`, never from the model.
- The negotiator never states anything false: pickup windows come from real Lugg estimates, payment claims match what OWNER will actually do, no "I'm just around the corner."
- Polling stays ≥30 min with jitter (upstream default). Do not "optimize" it faster.
- Escalate to OWNER (Telegram) on: deal agreed, seller asks for a call, any scam flag, anything off-script.
- Secrets come from environment variables or untracked local files. Never commit tokens; `.gitignore` already covers the usual suspects.

## Architecture

```
SCOUT (upstream monitor, 30–60 min jittered polls)
  → SCORE   scoring/brain.py  → schema.DealVerdict (structured, not vibes)
  → NEGOTIATE  negotiation/playbook.py (deterministic $) + messenger.py (Playwright) + LLM prose
  → CLOSE   payments.py (prefill links) + closing/lugg.py + approvals/telegram_bot.py (the card)
  → HAUL    booking prefill, mover-day coordination, photo-at-door triggers OWNER's payment tap
```

State machine in `state.py` (sqlite, stdlib only): `spotted → scored → (passed | watching | inquiring) → negotiating → agreed → awaiting_approval → scheduled → done`, with `dead` reachable from anywhere. One listing = one row; verdicts and thread transcripts as JSON columns. The state machine is the cure for "I lose track of things" — nothing depends on OWNER's memory.

## Upstream (`ai-marketplace-monitor`) notes

- **AGPL-3.0**, actively maintained (v0.10.2, Jul 2026). Installed via pip, NOT vendored. If this project is ever distributed or hosted for others, AGPL obligations apply to combined work — keep our code cleanly separated and see the productization section of docs/plan.md.
- Playwright **sync** API, **headed**; login pauses ~60s (`login_wait_time`) for manual captcha/2FA — that's by design, keep a human able to intervene.
- `facebook.py` CSS selectors are the fragile part; expect breakage when FB shifts layout. Fix selectors, don't fight detection.
- Config: TOML at `~/.ai-marketplace-monitor/config.toml`. AI backends include Anthropic. Telegram notifications built in. Diskcache dedupe + price-drop re-alerts.
- Phase 1 will likely need a **fork** (its AI hook returns a 1–5 rating; we want a structured `DealVerdict`). Fork on GitHub under OWNER's account, keep the diff minimal and rebased on upstream.

## Dev conventions

- Python ≥3.10, `src/` layout, pydantic v2 models live in `schema.py`.
- Setup: `pip install -e ".[dev]"` then `pytest -q`. On the Windows box: `py -m venv .venv` then `.venv\Scripts\activate`.
- Tests must stay hermetic (no network, no keys, no Facebook). Anything that talks to the world gets a thin adapter so the logic stays testable.
- Every module carries a "Phase N" docstring — keep them and the **Current status** section above truthful as work lands.

## Phase acceptance criteria

- **P1:** new listing → validated `DealVerdict` + Telegram card with buttons within ~2 min of the poll that found it.
- **P2 warm-up:** drafts land in Telegram; OWNER taps send; zero sends occur outside `Guardrails`. **P2 auto:** agreements reached with every send inside the rails; escalation triggers fire in tests.
- **P3:** on AGREED, the card contains a working Venmo prefill link, a Lugg estimate, and proposed windows; approval advances state to `scheduled` with one tap per money/booking action.

## References

Full plan + research sources: `docs/plan.md` (private) · Upstream: https://github.com/BoPeng/ai-marketplace-monitor · Lugg rate math (with source URL) is in `closing/lugg.py`.

## Phase 1 runbook (sidecar mode)

1. `pip install -e ".[dev]"` in the venv (new deps: httpx, diskcache, geopy), then `pytest -q` — 50 green, no network.
2. Switch the scout to scout mode: copy `configs/upstream-scout.toml` over `~/.ai-marketplace-monitor/config.toml`. Upstream keeps searching + caching exactly as before; it no longer scores or notifies — the sidecar owns all judging and Telegram traffic.
3. Set `SCOUT_HOME_ANCHOR` as a User env var ("lat,lon", or a place name / ZIP). Until set, distance gating anchors to downtown DC and prints a warning.
4. Run both processes: `scripts\run-radar.ps1` (upstream scout) and `scout run` (sidecar; `--once` for a smoke test). The sidecar polls the LOCAL cache + Telegram buttons every 5 min — zero additional Facebook traffic, so the ≥30-min rule is untouched.
5. New wants: `scout want add "describe the thing you want"` → writes `configs/wants/<slug>.toml` and prints the `[item.<slug>]` section to paste into the scout config. The slug is the join key between the two — they must match.
6. Card buttons: Watch (re-ping on price drop) · Kill · Draft opener (generates a copy-paste message; Phase 1 sends NOTHING to sellers — that stays true until Phase 2 earns autonomy through draft-mode).
