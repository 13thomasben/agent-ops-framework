---
name: webagent
description: Automate a task on a website that has no API — log into a portal, read a queue, pull published figures, check a dashboard — either as a one-off or as a scheduled job. Use when the user asks to "check the portal", "scrape", "pull data from <site>", "log into X and get Y", "monitor <page> for changes", "automate this website", or describes a recurring manual web check they want to stop doing by hand. Also use when the user wants to create, edit, run, or debug a webagent task file. Do NOT use when the target system has a working API or MCP connector — say so and use that instead.
---

# webagent

Drives a real Chromium browser with Claude to complete a task on a website, and
returns structured JSON. Tasks are declarative YAML files in `tasks/`.

Lives at `harnesses/webagent/`. `run.py` resolves its own paths, so the
commands below work from anywhere in the repo — `tasks/`, `config.yaml`,
`runs/`, and `state/` are always read and written inside the skill folder. Every
other path in this doc is relative to it.

## Setup (once per environment)

```bash
pip install -r harnesses/webagent/requirements.txt
python -m playwright install chromium
```

`ANTHROPIC_API_KEY` must be set. On a scheduled routine put the install lines in
the routine's **setup script**, and put `ANTHROPIC_API_KEY` plus any portal
credentials named in a task's `secrets:` in the routine's **environment
variables** — never in a file here. See `PROCESS.md`.

## Step 0: Should this be a browser task at all?

Work down this ladder and stop at the first hit. Do not skip it — reaching for a
browser when an API exists is the most common way this tool gets misused, and
the resulting automation is slower, costlier, and quietly unreliable.

1. **Official API** → use it.
2. **MCP connector already available** (Jira, Slack, HubSpot, Fireflies, Google
   Drive, Microsoft 365, a workflow vendor…) → use it. Call `tool_search` if it isn't loaded.
3. **Stable page, no API** → a plain Playwright script with no model in the loop
   is cheaper and more deterministic. Recommend that.
4. **Unstable or unfamiliar page, no API** → webagent. This is the actual use case.
5. **Site actively fights automation** (aggressive bot detection, ToS forbids it)
   → stop and tell the user, rather than trying to route around it.

If the user names a system that clearly has an integration, say so plainly before
building anything.

## Running an existing task

```bash
R=harnesses/webagent/run.py
python $R list                  # available tasks, schedules, missing secrets
python $R validate              # check every task file parses
python $R run <name>            # execute
python $R run <name> --headed --stdout   # watch it, print JSON
```

`python $R run smoke-test --headed --stdout` is the end-to-end install check —
it deliberately tries to leave its allowed domain and expects to be blocked.
`TESTING.md` has the full ladder: install check → does it fabricate → login and
session reuse → verbatim capture on a real table. Work through it before
pointing a task at a real portal, and re-run `test-honesty` after any edit to
the system prompt or the default model.

Exit code is `0` only on `completed`. `failed` and `aborted` both return `1`.

Report the `summary` and `status` to the user. Surface the `action_log` only if
something went wrong — otherwise it's noise.

## Creating a new task

Write a YAML file in `tasks/`. Required: `name`, `goal`, `start_url`,
`allowed_domains`. Copy a starting point out of `tasks/templates/` — either
`public-page.yaml` (read-only) or `authenticated-portal.yaml` (login, session
persistence, secrets) — into `tasks/` and rename it. Files under
`tasks/templates/` are deliberately not loaded as runnable tasks.

Four things to get right:

**Write `goal` as an observation spec, not a procedure.** "Capture the rate
exactly as written; do not compute or normalise" beats "click the third tab then
read the table." If you catch yourself writing click-by-click steps, the page is
stable enough for a plain Playwright script — go back to Step 0 item 3.

**Always define `result_schema`.** It becomes the input schema of the
`task_complete` tool, so the model is structurally constrained into the right
shape rather than asked politely for it. Downstream consumers get a contract.

**Scope `allowed_domains` tightly.** It's enforced in the browser on every
navigation and after every click, so a redirect can't carry the agent off-site.
List only what the task genuinely needs.

**Never put a credential in a task file.** `secrets:` holds ENV_VAR_STYLE *names*
only; validation rejects anything that looks like a literal. The agent fills them
via `browser_fill_secret` and never sees the values.

Then always: `python harnesses/webagent/run.py validate`, and a first run
with `--headed` so the user can watch it.

## Debugging a task that misbehaves

Symptoms map to fixes fairly reliably:

| Symptom | Fix |
|---|---|
| Reports data as absent when it's on the page | Content is below the fold. Add a line to `notes:` saying where to look. Raising `max_steps` rarely helps. |
| Loops on the same element | The click isn't landing. Run `--headed` and watch. Often an overlay or cookie banner is intercepting. |
| Hits the step cap | Goal is too broad. Split into two tasks. |
| Hits the cost cap | Too many screenshots, or a dense page blowing up every snapshot — lower `max_text_chars` / `max_elements` in `webagent/browser.py:snapshot` (no per-task field for these yet). |
| Returns plausible but wrong values | Most serious failure. Tighten `result_schema`, and make the goal insist on verbatim capture. |
| `net::ERR_TUNNEL_CONNECTION_FAILED` on every page | Not the site — the environment's network policy is refusing egress. Check `curl -sS "$HTTPS_PROXY/__agentproxy/status"`; `recentRelayFailures` names the blocked host. Run somewhere with web access. |
| Guardrail blocks something legitimate | Add the domain to `allowed_domains`, or the label to `extra_blocked_keywords`' inverse — set `allow_destructive: true` only with the user's explicit say-so. |

Always develop new tasks with `--headed`. Watching the browser resolves most
issues in one run.

## Scheduling

Nothing here schedules itself, by design. Wire it to whatever already runs:
cron, an n8n Schedule trigger, a Claude Code routine shelling out to
`python run.py run <task>`, or a workflow-vendor job. Configure the `webhook` sink to
post the RunResult JSON back into that system.

## Honesty requirement

A browser agent that invents a plausible number when it can't find the real one
is worse than useless — the output looks fine and gets trusted. The system prompt
treats `task_failed` as a first-class successful outcome. Preserve that when
editing prompts or goals, and never coach a task toward "give your best guess."

If a run fails, report the failure. Do not fill the gap from prior knowledge.
