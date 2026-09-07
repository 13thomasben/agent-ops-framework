---
name: run-health
description: Detect scheduled skill runs that did not happen and report them to #applied-ai. Use for "did everything run", "run health", "which routines are down", "did the scorecard go out", "why is #bdr-coaching quiet", "check the automations", or any question about whether a skill's scheduled run actually fired. Designed for a daily 6:30 PM ET sweep after the day's last skill runs, but valid ad-hoc. Works by looking for evidence that each registered skill ran inside its expected window — its own post in its delivery channel, its clean-run notice in #applied-ai, or a state/data commit — and posting a missed-run notice naming the skills with no evidence. It is deliberately an OUTSIDE observer: a run that dies before its own error handling cannot report itself, which is the exact failure this exists to catch. Reports absence of evidence, never a guessed cause. Silent when every registered skill ran. Also audits its own coverage and says which skills it is not watching.
---

# Run health

Finds the scheduled runs that **did not happen** and says so in `#applied-ai`.

**Reader-facing canvas:** `#applied-ai` carries a channel canvas describing this skill for the people who read its output — `docs/agent-canvases/applied-ai.md`. **Update it in the same change as any edit to the cadence, delivery surface, thresholds, or write authority here.** See *Changing an existing skill* in `PROCESS.md`.

**Audience:** the Owner (owns the skills), the CEO. The reader is deciding whether an automation needs fixing this evening.

**Channel:** `#applied-ai` (`C_EXAMPLE_APPLIED_AI`) — **private**, `@bot` must be invited.

**Schedule:** daily at **6:30 PM ET**, after the day's latest registered skill run (call-intel, 5 PM ET) has had time to finish and commit. Each run checks the windows that closed since the previous run.

**Runner: a Claude Code routine.** Per `README.md`, *How these run*. **No skill in this repo is run by a GitHub Actions workflow** — see the history in that section before adding one. **Created 2026-08-25: `ROUTINE_ID`** ("Run Health — daily 6:30 PM ET"), on the bot environment (`ENV_ID`), fresh session per fire, entry prompt `prompts/run-health.md`. Also recorded in `tracker/inventory.csv`.

**Both open questions about that routine were answered on 2026-08-31, and both had the wrong cause written here. Read this before acting on a quiet evening:**

- **The fires that produced nothing were not dead. They were parked on a permission prompt.** `get_session` on each one returns `SESSION_STATUS_REQUIRES_ACTION` with a `pending_action` for `mcp__Slack__slack_read_channel` — this skill's core read, the one it makes against every watched channel. The session stayed alive and answerable; nobody answered; the routine record flipped to `ABANDONED` around it.

  Of the first six nightly fires, four parked on a `slack_read_channel` call and were never answered; two ran to `SUCCEEDED` and posted full sweeps. One of those two took roughly 15 hours from fire to finish — not slow work, but a run parked until somebody happened to approve it, then finishing. The other completed in **11 minutes**, which is what this sweep actually costs. A fire that reads `ABANDONED` one minute and `SUCCEEDED` half an hour later is the same story caught mid-approval.

  **Cause is in `README.md`, *Permission prompts on routine runs* — corrected 2026-09-03.** It is not a missing allowlist and there is no fix in this repo: the connector proxy answers the call with `-32003 needs_approval` *after* the local permission layer has passed it, raises the approval card with always-allow suppressed, and pins the approval to that call's arguments. `.claude/settings.json` is correct and does load. Earlier text here blamed the environment's missing setup script and `scripts/install-routine-permissions.sh`; that script has been deleted and never addressed this. This skill is the most exposed of any in the repo, because it cannot do a single check without `slack_read_channel` and has no token path to fall back to.

  **What was written here before — "the logic is sound; the runner is not" — was wrong.** The runner started every fire on time, cloned the repo, loaded the skill and got as far as the first channel read. Do not go looking for flakiness in the executor.

  **A one-in-three watchdog is still worse than it sounds,** because its failures are silent by construction and look identical to a clean night. Treat a quiet `#applied-ai` evening as unknown, not healthy, for as long as this skill's reads go through a connector.

  **`ROUTINE_RUN_STATUS_ABANDONED` is not terminal, and neither is `PENDING`.** Never conclude a run failed from its status. And now there is a better check than artefacts: **`get_session` on the run's session.** A `pending_action` means the run is alive, recoverable, and tells you the exact tool it is waiting on — approve it in the Routines UI and it continues. `SESSION_STATUS_REQUIRES_ACTION` with `connection_status: disconnected` is the one shape that really is dead.

- **`state/sweeps.jsonl` was never dropped. It is sitting in unmerged pull requests.** Both successful sweeps wrote and pushed it — to the fire's own per-run branch, where a PR was opened and never merged. The next fire clones `main`, which does not have them, so every sweep is a first sweep. The second successful run diagnosed the symptom itself, unprompted:

  > *this run found `state/sweeps.jsonl` and `state/alerts.jsonl` empty, even though a "first sweep" notice was posted here four days ago — that run's state commit never landed. Treating tonight as a fresh first run per Step 1; the miss counts below start over, so an actual gap may be older than "1st miss" implies.*

  Its reading of the consequence was exactly right; only "never landed" was wrong. **Merging those PRs restores the ladder — nothing needs recomputing.** This is fleet-wide, not this skill's: 16 open per-run state PRs across eight skills as of 2026-08-31. Until they are merged routinely, the three-consecutive-misses escalation cannot fire, so this skill under-reports every gap as a first miss.

  That is the right behavior and also the precise cost: **without the state commit, every sweep is a first sweep.** Miss counts reset, the three-consecutive-misses escalation to the CEO can never trigger, and a skill that has been dark for a week reads as "1st miss". `acme-ticket-daily-check` reported the identical post-but-no-commit shape across five of its own runs, so this is the runner, not the skill — but it disables this skill's escalation ladder specifically, which is worth fixing ahead of the abandonment rate.

  **It is earning its keep on the fires that land.** The second successful sweep flagged five skills with no evidence of a run, noted one still missing three days after its first flag, correctly withheld a repeat notice on another under the one-notice-per-window rule, declined to alert on a skill whose own config says its routine is being recreated, and reported that `fleet-integrity-check` had a canvas but no registry entry so nothing watched it.

  **Connectors are attached** — Slack and GitHub, confirmed on the routine 2026-08-26. That corrects an earlier note in this file: creation stored none (the Routines MCP tool refuses the `connectors` parameter for this organization), but a later prompt update did attach them; the update response simply did not echo them. Slack and GitHub are the two this skill needs, so a missing connector is **not** the explanation for the abandoned run. Still confirm `SLACK_BOT_TOKEN` and `ANTHROPIC_API_KEY` are on the bot environment.
- **The cron is stored in UTC, not `America/New_York`.** It is `30 22 * * *`, which is 6:30 PM ET only while EDT is in effect. **On 2026-11-01 it must move to `30 23 * * *`**, or the sweep runs at 5:30 PM ET and closes windows an hour early — `acme-call-intel`'s 5:00 PM window would be judged 30 minutes after it opens, and a late-but-successful run would read as missing. This skill's grace period is 30 minutes, so the DST shift is larger than the tolerance.

**Checking that it is still sweeping:** `state/sweeps.jsonl` gets a row on every run, clean or not. That file, and only that file, is how anyone confirms this skill is alive.

**Posting identity:** `@bot` via the Slack Web API, per `contracts/slack-dispatch.md`.

**Reply handling:** registered in the cadence table in `contracts/thread-feedback.md` (14-day lookback). Step 0 **deliberately diverges** from that contract's four categories: `report_correction` / `data_fix` / `product_or_architecture` / `none` describe a skill that writes into systems of record, and this one writes nowhere but its own state. Its categories are *mute*, *fixed* and *wrong* instead. The shared rails that still bind are the ones that matter: skip your own replies, log every reply seen as the idempotency guard, and never act on a reply from outside the user map.

---

## Why this exists, and why it has to be an outside observer

Every skill here already reports its *own* trouble. `_shared/slack-dispatch.md` makes it repo-wide policy — *"a silent failure is worse than a post from the wrong identity"* — and the skills implement it: a failed dispatch falls back to a labeled post, an absent connector produces a degraded-run note, a run that finds nothing posts a clean-run notice so a quiet channel is never mistaken for a broken one.

All of that is self-reporting, and self-reporting has one hole it can never cover: **a run that never started, or died before reaching any of that code, has nothing to report with.** Nobody hears anything, and silence is indistinguishable from a quiet day.

That is not hypothetical. `acme-inbound-leads` was scheduled on a GitHub Actions workflow on 2026-08-21. It fired on 2026-08-22, 08-23 and 08-24 and died in under 20 seconds each time, before Claude Code even started, on secrets the repo does not have. Nothing reached any channel. It was found three days later only because someone happened to check.

So the detector has to sit **outside** the runs it watches, and it has to key on **absence of expected output** rather than on an error it will never see.

---

## Core principle

**Report the absence, not a diagnosis.** This skill knows one thing reliably: whether evidence of a run exists. It does not know why a run is missing, and a confident wrong cause ("HubSpot is down") is worse than none — it sends someone to fix the wrong thing. Name the skill, the window, and what evidence was looked for. Name a cause **only** when this run actually observed it, and say how it was observed.

---

## Hard rules

1. **Silent when everything ran.** No post on a clean sweep. A daily "all healthy" line is exactly the filler that trains people to skim `#applied-ai`, and this channel carries things that need acting on. The clean-run record lives in `state/sweeps.jsonl`, which is where to look to prove the sweep itself is running.
2. **Absence of evidence is the finding, not proof of failure.** Say "no evidence of a run" and name the three places checked. A skill can have run and delivered somewhere this skill does not watch; that possibility goes in the notice rather than being asserted away.
3. **Never re-alert identically.** One notice per skill per missed window. A skill missing for days gets **one** escalating line carrying the streak, not a fresh identical post every evening. See *Escalation and mute*.
4. **Never infer a cause from a pattern.** Two skills missing on the same day does not mean a shared outage. Report both; say they share a day if that is useful; do not name a common cause this run did not observe.
5. **Report your own coverage gaps.** A registered skill that is silently absent from `config.yaml` is watched by nobody while the channel looks healthy. Step 3 checks the registry against `docs/agent-canvases/channels.json` every run and names anything unwatched.
6. **Read-only outside `#applied-ai` and this skill's own state.** This skill never restarts a routine, never re-runs a skill, never touches HubSpot, Jira, Confluence or another skill's files. It reports; a human acts.

---

## Write surfaces

**Write surfaces:** classified per `contracts/write-surfaces.md` (reversibility · record ownership · **audience** · **attribution**). Re-run that gate on any change that widens what or where this skill writes.

| Write | Audience | Attribution | Verdict |
|---|---|---|---|
| Slack `#applied-ai` post + thread replies (`@bot`) | `internal-only` | `bot-identity` | auto |
| Repo `state/sweeps.jsonl`, `state/alerts.jsonl`, `state/reply-log.jsonl` | `internal-only` | `bot-identity` | auto |
| Every other system (HubSpot, Jira, Confluence, Outlook, other skills' files, routine config) | — | — | **NEVER** — read-only by design; this skill reports, it does not remediate |

---

## Required context

- **Delivery channel:** `#applied-ai` → `C_EXAMPLE_APPLIED_AI` (**private**, `@bot` must be invited).
- **Registry:** `config.yaml` in this folder — one entry per watched skill, with its cadence, the window it must run in, and where to look for evidence. **This file is the whole behavior.** A cadence changed in a `SKILL.md` and not here makes this skill wrong in the quiet direction.
- **People to tag:** the Owner (`U_EXAMPLE_OWNER`) on every notice — they own the skills. The CEO (`U_EXAMPLE_CEO`) **only** when a skill has missed **3 or more consecutive windows**, which is no longer a blip.
- **Timezone:** all windows are evaluated in **America/New_York**. `config.yaml` records each cadence in ET regardless of the timezone its own report is written in (`bdr-call-coaching` reports in PT; its window is still stored ET).

### State files (`state/`, git-backed)

| File | Contents |
|---|---|
| `sweeps.jsonl` | one row per sweep: `{run_at, window_start, window_end, checked, healthy, missing, unwatched}`. The record that the sweep itself ran, including on clean days when nothing is posted |
| `alerts.jsonl` | one row per missed window alerted on: `{skill, window_start, window_end, first_alerted_at, consecutive_misses, ts, status}`. `status` is `open`, `resolved` or `muted`. The idempotency ledger — a window present here is never alerted on twice |
| `reply-log.jsonl` | one row per reply seen on a notice, with `category` and `action_taken` |

**Commit all three at the end of every run.** A git commit is the write; anything uncommitted is lost when the next run starts from a fresh checkout.

---

## Step 0 — Read replies on prior notices

Read the last **14 days** of this skill's own threads in `#applied-ai` (`conversations.history` with the bot token, then `conversations.replies`), matching the top-level shape `*Missed scheduled runs*`. Skip `@bot`'s own replies (`U_EXAMPLE_BOT`) and any `reply_ts` already in `state/reply-log.jsonl`.

Three categories matter here:

| Reply | Meaning | Action |
|---|---|---|
| **Mute** — "paused", "expected", "we turned that off", "on hold" | The miss is intentional | Set that skill's open alert to `muted`. Stop alerting on it **until it runs successfully again**, then clear the mute automatically and resume watching. Echo `*Muted:*` in the thread |
| **Fixed** — "fixed", "routine restarted", "should be running now" | Someone acted | Leave the alert `open`. **Do not mark it resolved on a claim** — resolve it only when evidence of an actual run appears. Echo `*Noted:*` and say the next sweep will confirm |
| **Wrong** — "it did run, it posts to #X" | This skill looked in the wrong place | Post a corrected reply, and route a `config.yaml` fix to the batch in Step 5. Registry edits are code changes, not runtime writes |

**A mute is not a fix.** Muting hides a real outage if it was given carelessly, so a mute always names who gave it and when, and is cleared by a successful run rather than by time.

---

## Step 1 — Compute the windows that closed

For each entry in `config.yaml`, work out whether its window closed since the previous sweep (`state/sweeps.jsonl`, newest row) and is therefore due for checking now.

- **Daily** entries close their window at `expected_by` each day the cadence covers. `days: weekdays` means Mon–Fri only: a weekday-only skill silent on Saturday is correct, and alerting on it is the fastest way to get this skill ignored.
- **Weekly** entries close at `expected_by` on their named day.
- **A window still open is not checked.** A skill due at 5 PM is not missing at 4 PM.
- **First run, or a lost `state/` directory:** check only the single most recently closed window per skill. Do not sweep history and fire a backlog of alerts for days nobody can now act on.

Grace: treat a window as closed **30 minutes after** `expected_by`, so a run that starts on time and takes a while to post is not called missing. Routine start times drift by a few minutes; the grace absorbs that.

---

## Step 2 — Look for evidence each skill ran

Three independent signals. **Any one is sufficient** — a skill that posted its report but failed to commit state still ran.

1. **Its own output** in its delivery channel, inside the window. Match the `evidence.message_shapes` patterns from `config.yaml` on **message text, not author** — the same rule Step 0 of the other skills uses, and for the same reason: history predates `@bot`, and a fallback post is authored by a human account.
2. **Its clean-run notice** in `#applied-ai`, inside the window. This is what a skill posts when it ran and found nothing, and it is the signal that separates "ran, quiet day" from "did not run".
3. **A commit** touching its `state/` or `data/` paths, inside the window (`git log --since --until -- <paths>` on `main`).

Found any → **healthy**. Record it and move on.

Found none → **missing**. Record `{skill, window, signals_checked}` — the three places, named, so the notice can say what was looked for.

**Reads use the bot token for `#applied-ai` and `#inbound_leads`** (private, and `@bot` is a member), and the Slack MCP connector for the rest. Per `slack-dispatch.md`, MCP connectors are not guaranteed on a scheduled run: **if the connector is missing, say so in the notice and mark those skills `unchecked` rather than `missing`.** Reporting a skill as down because this skill could not look is the worst output it can produce.

---

## Step 3 — Audit your own coverage

Every run, compare `config.yaml` against `docs/agent-canvases/channels.json`:

- A skill in `channels.json` with **no** `config.yaml` entry and not in `coverage.intentionally_unwatched` → **unwatched**. Name it.
- A `config.yaml` entry naming a skill that no longer exists → **stale**. Name it.

Report both in the notice's footer, and in `sweeps.jsonl` even on a clean sweep. **A watchdog with silent gaps is worse than no watchdog**, because the channel's quiet reads as "everything is fine" when it means "nothing is being watched".

---

## Step 4 — Decide whether to post

| Missing skills | Unwatched or stale | Action |
|---|---|---|
| 0 | none | **Post nothing.** Append the sweep row and stop |
| 0 | some | **Post nothing this run.** Carry it into the next notice's footer, and surface it in the weekly-cadence reminder rather than as its own post. A coverage gap is not urgent enough to earn a message on a healthy day |
| 1+ | any | Post per Step 5 |

Skills whose only open alert is `muted`, or already alerted for this same window, do not count toward the total — that is rule 3.

---

## Step 5 — The notice

One message, all missing skills, headed:

```
*Missed scheduled runs* · [window covered]
```

Then one bullet per skill:

```
• *[skill]* — expected [cadence] by [time] ET, no evidence of a run. Checked: its post in [channel], a clean-run notice in #applied-ai, a commit to [paths]. [Nth consecutive miss.]
```

Close with the owner tag, and the coverage footer when there is one:

```
<@U_EXAMPLE_OWNER>
_Not watched: [skills]. Registry: `skills/run-health/config.yaml`._
```

Formatting follows the repo's Slack conventions: single-asterisk `*bold*`, `<url|label>` links, bare `<@USERID>` tags, `•` bullets, no emoji, and keep the message under 3,500 characters (Slack splits near 4,000 and returns only the tail's `ts`, which orphans the thread Step 0 needs).

### Escalation and mute

- **1st and 2nd consecutive miss:** tag the Owner only.
- **3rd or later:** add the CEO (`<@U_EXAMPLE_CEO>`) and lead the bullet with the streak. Three days is no longer a blip.
- **A skill already alerted for its current miss** is not re-posted. It reappears only when the streak count changes, and then as one line inside that evening's notice, never as its own message.
- **Resolution is by evidence.** When a previously-missing skill produces evidence again, set its alert `resolved` and post one `*Recovered:*` reply in the original thread. The recovery reply is worth the noise: it closes the loop for whoever was asked to fix it.

Post with `chat.postMessage` and the bot token, keep the returned `ts` in `alerts.jsonl`, and follow the labeled-fallback rule in `slack-dispatch.md` if the dispatch path fails.

---

## What this does not cover

Written down because a monitor that looks complete and isn't is the failure it exists to prevent.

- **A run that happened but produced wrong output.** This checks that something appeared, never whether it was right. A skill posting nonsense on schedule reads as healthy here.
- **A run that started and hung.** No evidence appears, so it surfaces as missing — correct outcome, misleading label. The notice says "no evidence of a run", which covers both.
- **Anything not in `config.yaml`.** Step 3 exists so the gap is visible rather than assumed away.
- **This skill itself.** If its own routine dies, nothing reports it, and `#applied-ai` goes quiet in exactly the way it is meant to detect. That is a real single point of failure, not a solved problem. It shrinks the blind spot from every skill to one, and `state/sweeps.jsonl` is the place to confirm the sweep is still running — the newest row's `run_at` is the answer. **Do not paper over this with a daily heartbeat post**; that reintroduces the filler rule 1 forbids, and a heartbeat nobody reads fails silently too.
