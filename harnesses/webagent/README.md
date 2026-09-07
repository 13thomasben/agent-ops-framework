# webagent

A task-driven browser agent. You write a YAML file describing what you want done
on the web; Claude drives a real Chromium browser to do it and hands back
structured JSON.

Built to be triggered from something else — cron, n8n, a workflow-vendor job, a Claude
Code routine. It has no scheduler of its own on purpose. You already have one.

Installed in this repo at `harnesses/webagent/`. Paths below are relative to
that folder; `run.py` resolves its own, so `python harnesses/webagent/run.py
…` works from the repo root and still keeps `runs/` and `state/` inside the skill
folder. `SKILL.md` is the short operating guide — this file is the deeper one.

---

## Architecture

```
  task YAML ──► agent loop ──► tool call ──► browser ──► real page
  (the ask)     (Claude)       (guardrail)   (Playwright)
                    ▲                             │
                    └────── snapshot / result ◄───┘
                                  │
                            RunResult JSON
                                  │
                    ┌─────────────┼─────────────┐
                  file          Slack        webhook
                                            (n8n / vendor)
```

Four moving parts:

| File | Job |
|---|---|
| `webagent/task.py` | Loads and validates YAML task specs. Builds the system prompt. |
| `webagent/browser.py` | Playwright wrapper. Snapshots pages, executes actions, enforces guardrails. |
| `webagent/agent.py` | The loop. Model → tool → observation → model, with three circuit breakers. |
| `webagent/sinks.py` | Where results go afterwards. |

**The key design choice** is that the model never sees a CSS selector. Each
snapshot stamps the DOM with `data-wa-ref="N"` and returns a numbered list:

```
[1] a "Other page"
[2] input "Username" (empty)
[3] input:password "Password" (password field)
[4] select "Tier A Tier B" (options: a | b)
[5] button:button "Sign in"
```

The agent says "click 5". That indirection is what makes it survive a CSS class
rename, which is the thing that breaks brittle scripted automation.

---

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium

export ANTHROPIC_API_KEY=sk-ant-...
```

Verify the whole stack end to end before pointing it anywhere real:

```bash
python run.py run smoke-test --headed --stdout
```

That task deliberately tries to navigate off-domain and expects to be blocked.
If it reports `guardrail_blocked_offdomain: true`, everything is wired up.

```bash
python run.py list        # what's available, with schedules and missing secrets
python run.py validate    # check every task file parses
python run.py run <name>  # go
```

Useful flags: `--headed` (watch it work — use this constantly while developing a
new task), `--stdout`, `--model`, `--max-steps`.

---

## Templates

`tasks/templates/` holds two starting points — `public-page.yaml` (read-only) and
`authenticated-portal.yaml` (login, secrets, session persistence). They are *not*
loaded as runnable tasks; copy one into `tasks/`, rename it, and point it at a
real target.

`tasks/smoke-test.yaml` is the only task that ships ready to run.

## Anatomy of a task

```yaml
name: rate-watch          # tasks/rate-watch.yaml
goal: |
  Find the published financing rate tiers on this page. For each, capture the
  tier name, the rate exactly as written, and the term in months.
  Record values verbatim. Do not compute or normalise anything.

start_url: https://example.com/rates
allowed_domains: [example.com]      # hard boundary, enforced in the browser

max_steps: 20
max_cost_usd: 0.35

result_schema:                       # becomes the task_complete tool's schema
  type: object
  properties:
    tiers:
      type: array
      items:
        type: object
        properties:
          tier_name: {type: string}
          rate_as_written: {type: string}

sinks:
  - type: file
  - type: slack_webhook
    url_env: SLACK_WEBHOOK_URL
```

Three things earn their keep here:

**`result_schema` is not decoration.** It becomes the input schema of the
`task_complete` tool, so the model is structurally constrained into your shape
rather than asked politely for it. Downstream consumers get a stable contract.

**Write the goal as an observation spec, not a procedure.** "Capture the rate
exactly as written" beats "click the third tab then read the table." If you find
yourself writing click-by-click steps, the page is stable enough that plain
Playwright would be cheaper and more reliable — use that instead.

**`allowed_domains` is enforced at the browser, not in the prompt.** A prompt
instruction is a suggestion. This is a wall.

---

## Guardrails

Four layers, all enforced in `browser.py` where the model can't talk its way past
them:

1. **Domain allowlist** — checked on every navigation *and* after every click, so
   a redirect can't carry the agent somewhere it shouldn't be. Subdomains of an
   allowed domain pass; lookalikes (`notexample-lender.com` vs
   `example-lender.com`) do not.

2. **Destructive-action blocking** — clicks on elements labelled *delete, pay
   now, approve, submit payment, transfer funds, publish, terminate*… are refused
   before they fire. Set `allow_destructive: true` per task to lift it, and add
   your own terms via `extra_blocked_keywords`. It's a blunt instrument matching
   on visible label text; treat it as a seatbelt, not a vault.

3. **Secrets by reference** — `browser_fill_secret` takes an env var *name*. The
   value is read inside the process and typed into the field. It never enters the
   model's context, so it never lands in a prompt log or a run artifact. Secrets
   not declared in the task's `secrets:` list are refused even if the model asks
   for them by name.

4. **Three circuit breakers** — steps, wall clock, and dollars. Each catches a
   different failure: an agent looping on a broken element, a page that hangs, and
   a run that's technically progressing but not worth what it's costing.

On top of that, the system prompt leans hard on refusing to fabricate. A browser
agent that invents a plausible number when it can't find the real one is worse
than useless, because the output *looks* fine and will be trusted. `task_failed`
is treated as a first-class successful outcome.

---

## Scheduling

Nothing here schedules itself. Pick whichever you already run:

**cron** — put the `schedule:` string from the task file into your crontab:

```cron
0 7 * * 1-5  ANTHROPIC_API_KEY=... /usr/bin/python3 /path/to/acme-skills/harnesses/webagent/run.py run rate-watch >> /var/log/rate-watch.log 2>&1
```

**n8n** — Schedule trigger → Execute Command, or run this behind a small HTTP
wrapper and use an HTTP Request node. Point the `webhook` sink back at an n8n
webhook to close the loop.

**Claude Code routine** — a routine can shell out to `python run.py run <task>`,
which gets you the cloud-hosted trigger without your laptop being open.

**Workflow vendor** — the `webhook` sink posts the full RunResult as JSON, so a browser task
becomes just another data source feeding a workflow.

The exit code is `0` only on `completed`, so any of these can alert on failure
without parsing output.

---

## Swapping in managed browser infrastructure

Local Chromium is right for development and fine for low-volume scheduled runs
on a box you control. When you need it to survive at scale — anti-bot handling,
proxies, parallelism, session replay — put a CDP URL in `config.yaml`:

```yaml
defaults:
  cdp_url: "wss://connect.browserbase.com?apiKey=..."
```

Browserbase, Steel, Browserless, and Kernel all speak CDP. Nothing else in the
project changes.

---

## When not to use this

Reach for an API first, every time. Browser automation is the most failure-prone
layer in any stack, and the failures are quiet — a selector shifts, a modal
appears, and you get a confident report built on a page the agent misread.

Concretely: don't point this at anything with a real API. Use the API. This is
for the systems that genuinely have no other door — legacy lender portals,
bureau sites, state filing systems, vendor dashboards that never shipped an
integration.

A rough decision order:

1. Official API → use it
2. MCP connector → use it
3. Stable page, no API → plain Playwright script, no LLM in the loop
4. Unstable page, no API → this
5. Site actively fights automation → reconsider whether you should be doing this

---

## Known limits

- **Single tab.** No multi-tab or popup handling. Add it in `browser.py` if a
  target needs it.
- **`allow_destructive` is all-or-nothing per task.** There's no per-action
  human-in-the-loop approval. If you want that, add a `confirm` sink that pauses
  and waits.
- **No retry logic across runs.** A failed run is just a failed run; your
  scheduler decides whether to retry.
- **Cost figures in `agent.py` are hardcoded.** Verify them against current
  pricing before trusting the dollar cap with real money.
- **iframes are not traversed.** The snapshot only walks the top document.
