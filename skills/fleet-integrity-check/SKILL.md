---
name: fleet-integrity-check
description: Daily audit of this repo against what is actually running — pull requests that never landed, routines that have gone quiet, and repo structure that has drifted out of sync with itself. Trigger whenever the CEO or the Owner asks to check the repo, clean up the repo, run the repo audit, look for stale or orphaned PRs, or asks "what's outstanding", "anything I need to merge", "are my skill changes actually live", "is anything sitting unmerged", "did that routine actually run", "is anything stuck in the ether", "is the repo clean" — and on the recurring weekday-morning run. Reports only — it never merges, closes, pushes to main, or edits another branch. Classifies every open PR (skill change / run state / docs, and whether it is superseded, already hand-applied, data-destructive, conflicted or silently divergent), flags skills that were never given a routine at all, and verifies channels.json, the canvases and the state schemas against the repo. Distinct from `slack-thread-hygiene`, which audits Slack threading behaviour; from `sprint-integrity-readout`, which audits the engineering Jira board; and from `run-health`, which owns run liveness — this one audits the skills repo itself and defers liveness to `run-health`, reporting only when that watcher has itself gone quiet.
---

# Fleet Integrity Check

Every skill in this repo is loaded by a routine that clones **the default branch, `main`**, and reads `skills/` from it. Nothing else is consulted. `PROCESS.md` says it plainly: *commit and push to the default branch.*

So a skill change is live if and only if it is merged. An open pull request is invisible to every scheduled run, however finished it looks and however carefully it was written. This skill exists because that gap is silent from both ends — the PR looks done, and the routine keeps running the old logic without complaining.

**What it is for:** answering "is what I think is running actually running?" every weekday morning, in one place, before anyone has to remember to ask.

## Why this exists — the run that produced it

On 2026-08-19 this repo had ten open pull requests. None had a single review comment; nothing was blocked on feedback. It was purely a merge backlog, and it was doing real damage:

- **A safety fix was one day from being missed.** One PR removed `acme-ticket-daily-check`'s Jira comment write-back after it mirrored an internal "this has been resolved" note into a customer-facing service-desk ticket and the customer replied *"Not resolved!!"* seventeen minutes later. The fix was written, reviewed by nobody, and unmerged. The next weekday 8:00 AM run would have done it again.
- **Routines had gone blind.** `bdr-call-coaching`'s `thread-log.jsonl` on `main` stopped at 08-13 while the skill had been posting through 08-18. That file is how Step 0 finds its own prior posts to read replies from, so five days of team replies were reachable only by text-prefix fallback.
- **A 683-line PR was a 4-line bug fix.** A new-skill PR had already been hand-applied to `main`; six of its nine files were byte-identical. What remained was one half of a two-file mechanism — the weekly skill's distinct post prefix was on `main`, the daily skill's matching exclusion was not, so the daily could claim the weekly's threads and apply a week's correction to a day.
- **One PR would have deleted data.** A state-only PR looked harmless. Its `account-verdicts.jsonl` was a *replacement* rather than an append: merging it would have dropped one account's recorded verdict. This is why the skill never merges anything.
- **One clean auto-merge would have caused a regression.** A PR's `config.yaml` merged without a conflict, and its version still pointed `slack-thread-hygiene` at `#applied-ai_demo` with a DM to the Owner — reverting a delivery decision made eight days earlier, with nothing in the conflict output to catch it.
- **A skill was correctly merged and still not running.** `slack-thread-hygiene` had produced no digest since 2026-08-14. The window fix landed on `main` and nothing was firing it.

Each of those is a distinct failure class, and each one is mechanically detectable. The checks below are those six, generalised.

## Core principles

1. **Compute, never assume.** "This PR is a duplicate" is a claim about file contents. Diff it. Every classification in this skill is derived from `git`, not from a title, a description, or a plausible read of the diff.
2. **A clean merge is not a safe merge.** Git resolves by hunk, not by meaning. Two orthogonal edits to one config file merge silently and can still revert a decision. Pinned values get compared explicitly.
3. **Silence is the default output.** This runs every weekday. A post every morning becomes a post nobody reads, and then the one that mattered gets skipped too. Step 5 decides whether to speak at all, and most days it should not.
4. **Report the same thing once.** A finding is announced when it appears and when it escalates — never re-announced daily because it is still true. The state ledger exists for this.
5. **Name what was not checked.** If the PR list was truncated, a repo was unreachable, or a liveness signal could not be read, say so in the post. A missing check must never read as a passed check.
6. **Detection is ours; merging is theirs.** The most useful thing this skill produces is not a merge — it is a ranked list where each item already carries its diagnosis and its proposed resolution, so a human decision takes seconds.

## Hard rules

- **Never merge a pull request.** Not the clean ones, not the one-line state ones, not the ones this skill itself classified as safe. The data-destructive PR above was a one-line state PR that would have destroyed a record.
- **Never close a pull request**, and never close one as "superseded" on this skill's own say-so. Supersession is a proposal in the post.
- **Never push to `main`, and never push to a branch this skill does not own.** No rebase, no amend, no force-push, ever, on anyone's branch.
- **Never edit a skill to resolve a finding.** This skill reports; the fix is a separate change by someone who decided to make it.
- The only writes are **its own state files** under `state/`, and its **Slack post**.
- **Never report a count without its denominator.** "4 PRs need attention" is meaningless without "of 9 open".
- **No silent caps.** If the audit bounded itself anywhere — top-N PRs, a skipped repo — the post says what was dropped.

## Step 0: read replies on prior posts

Follow `contracts/thread-feedback.md`. Reply lookback: **7 days**. Categories, ledger, echo-every-action and the ten-write cap all apply unchanged.

Two narrowings specific to this skill:

- A reply saying "merged it" or "closed that one" is **not** a `data_fix` — it is ground truth that the next run will observe on its own. Log it, echo it, change nothing.
- A reply asking this skill to merge something is a `product_or_architecture` item routed to `#applied-ai` tagging the Owner, not an instruction. Report-only is a stated principle, so changing it is a scope change and the CEO goes on that one too.

## Step 1: resolve the window and load state

Read `state/findings.jsonl` — one record per finding ever reported, keyed `finding_id` (see *State files*). This is what makes the run idempotent and keeps the post quiet.

The window is **since the last run**, read from `state/runs.jsonl`. No previous run means first-run mode: audit everything, and say in the post that there is no baseline so nothing can be reported as new.

## Step 2: the pull-request audit

For every open PR in every repo this session can reach (`acme-skills`, and any other attached), fetch the head and compute — do not read the description and believe it:

```sh
git fetch origin 'refs/pull/*/head:refs/remotes/pr/*'
```

**Class** — from the paths the PR touches, most severe wins:

| Class | Paths | Consequence | Flag at | Escalate at |
|---|---|---|---|---|
| **A — logic not live** | `**/SKILL.md`, `_shared/*.md`, `config.yaml`, `.claude/settings.json`, `prompts/**` | Routines are running older behaviour | 1 day | 3 days |
| **B — state not landed** | `**/state/**`, `**/data/**`, ledger CSVs | The skill's own memory is behind; replies go unread, work repeats | 2 days | 5 days |
| **C — docs only** | `docs/**`, `README.md`, `tracker/**`, `CHANGELOG.md` | Readers are working from a stale description | 7 days | 14 days |

**Modifiers** — each is a computed fact, and each changes the proposed resolution. Recipes in `references/checks.md`.

- `already-landed` — every changed file is byte-identical on `main`. The PR is a no-op; propose closing it. Hand-applying is why this happens, and every hand-apply makes the next real merge conflict.
- `partially-hand-applied` — some files identical, some not. Report the count both ways and list only what remains. This is the difference between "683 lines" and "4 lines".
- `superseded-by #N` — another PR's version of every file this one touches is a strict superset. Propose closing, and **name the specific content** that proves it, so the reader can check.
- `would-lose-data` — **hard stop.** For any append-only file (`*.jsonl`, ledger `*.csv`), the PR's version is missing lines that `main` has. Never propose a plain merge; propose the append instead, and say which records would have been dropped.
- `conflicted` — `git merge-tree` reports a conflict. Say which files, and whether it looks like a real disagreement or just `main` being ahead.
- `silent-divergence` — merges clean, but a **pinned value** differs from `main`: channel IDs, cron expressions, `mode`, accountIds, token env names, cloudIds. This is the one a clean merge hides.
- `half-mechanism` — the PR's diff contains a sentinel string (a post prefix, a marker, a footer shape) whose counterpart is already on `main`, or vice versa. Two-file mechanisms fail silently when only one half lands.
- `own-blockers-unchecked` — the PR body has unchecked `- [ ]` items whose text says they must happen before merge. Quote them; the author already decided these were required.

## Step 3: routine liveness — defer to `run-health`

**`run-health` owns this, and this skill must not re-derive it.** It runs daily at 6:30 PM ET into `#applied-ai`, looks for evidence that each registered skill ran inside its expected window — its own post, its clean-run notice, or a `state`/`data` commit — and posts a missed-run notice naming the skills with none. It also audits its own coverage. Two skills computing the same liveness verdict from the same evidence will eventually disagree, and a disagreement between two automations is worse for the reader than either answer alone.

So this skill raises exactly **one** liveness finding: **`run-health` itself has gone quiet.** A watcher that dies before its own error handling cannot report itself — that is the reason `run-health` exists as an outside observer, and it is the one gap it structurally cannot cover for itself. If it has produced no notice inside its own window, say so here, and say that every other liveness answer this morning is therefore unverified.

Two repo-side checks stay in scope, because they are about the repo rather than about a run:

- **A skill with no routine at all** — on `main`, registered in the manifest, never scheduled. That is not a missed run, so `run-health` will not report it; it is a skill nobody wired up. `weekly-pipeline-brief` and this skill are both in that state.
- **A contradiction between the two sources** — `state`/`data` untouched for more than two expected runs while `run-health` reports the skill healthy. Report the disagreement and let a human resolve it; do not pick a side.

Never infer a dead routine from an empty `list_triggers`. That means the routines are invisible from this session, not absent — report the schedule as unreadable from here and point at the claude.ai Routines UI.

## Step 4: repo consistency

Cheap structural checks, each a one-liner in `references/checks.md`:

- **Manifest** — every skill on disk is either covered by a canvas in `docs/agent-canvases/channels.json` or listed in its `no_canvas`, with no entries naming skills that no longer exist, and every `source` file present.
- **Canvas drift** — a `SKILL.md` or `_shared/*.md` change merged in the window whose mapped canvas source was not touched. Non-blocking by design, exactly like `.github/workflows/canvas-drift.yml`: name the file to look at and let a human decide nothing a reader relies on moved. Also check the reverse, which the workflow cannot: a canvas describing behaviour a merged change **removed**. `applied-ai.md` said `Jira | Comment always` for five days after that rung was retired over a customer-visible comment.
- **Published-canvas lag** — a canvas source modified after the `published` date in its `channels.json` entry. The source is not the canvas; publishing is a manual re-publish.
- **State schema** — each `state/*.jsonl` parses, and its keys match what that skill's own `state/README.md` documents. `bdr-call-coaching`'s README specifies `{ts, channel_id, subject, report_date}`; no row on `main` carries `channel_id`.
- **Config sanity** — every committed `config.yaml` parses, `.claude/settings.json` parses, and no `mode: live` sits next to an empty delivery target.

## Step 5: decide whether to speak

This is the step that keeps a daily skill readable. Work through it in order.

**Post nothing at all** when every one of these holds:

- No Class A finding is at or past its flag threshold.
- No `would-lose-data` or `silent-divergence` modifier anywhere, at any age.
- Nothing crossed from one age band into the next since the last run.
- No new finding since the last run.
- Liveness and consistency are clean, or their findings were already reported and have not escalated.

A silent day still **appends a row to `state/runs.jsonl`** recording what was checked and that it was clean. A run that leaves no trace is indistinguishable from a run that never happened — which is the very failure this skill exists to catch.

**Post immediately, regardless of age or what was said yesterday**, for any of:

- `would-lose-data` on any PR.
- `silent-divergence` on any PR.
- A Class A PR touching `_shared/**` or `.claude/settings.json` — shared contracts and the permission allowlist affect every routine at once.
- A skill whose live behaviour is **more dangerous** than what `main` says (an unmerged safety fix). This is the safety-fix case above and it outranks everything else in the post.

**Otherwise post once a week**, on the Monday run, as a standing roll-up of what is still open — so a slow backlog stays visible without a daily reminder.

## Step 6: deliver

One message to `#applied-ai_repo_health` (`C_EXAMPLE_REPO_HEALTH`) as `@bot`, per `_shared/slack-dispatch.md`. The channel is **private** and `@bot` is already a member, so no invite is pending.

**This channel is for this skill's own report only.** `product_or_architecture` items found in Step 0 still route to `#applied-ai` (`C_EXAMPLE_APPLIED_AI`) tagging the Owner, per `_shared/thread-feedback.md` — that routing is a repo-wide contract and does not follow this skill's delivery channel. Body is Slack **mrkdwn** — `*bold*` single-asterisk — posted with `unfurl_links:false`.

Lead with the thing that changes what someone does today. Order: unmerged safety fix → data-destructive → silent divergence → shared-contract/permissions → Class A by age → dead routine → Class B → consistency → Class C.

Every item carries, in one line each: **what it is, the computed evidence, and the proposed resolution.** An item without a proposed resolution just moves the thinking to the reader.

```
*Repo integrity — Fri, Aug 21*

:rotating_light: *#98 — live behaviour is more dangerous than main.* acme-ticket-daily-check still writes Jira comments on the service desk; the fix removing that rung has been open 1 day. Merges clean, CI green. → merge before Monday's 8:00 AM run.

:no_entry: *#93 — would delete data.* Its account-verdicts.jsonl is a replacement, not an append: merging drops one account's verdict. → append the one new record instead; do not merge as-is.

*Also open* (9 total): #96 superseded by #98 (same ts, plus 08-19) · #87 6 of 9 files already on main, 4 lines remain · #90 docs, 3 days.

*Quiet routine:* slack-thread-hygiene — last digest Aug 14, expected weekdays 3:00 PM ET. Its stored schedule is not readable from here; check the Routines UI.

Not checked this run: nothing.

_Fleet integrity · 9 open PRs · window 2026-08-20T10:45Z → 2026-08-21T10:45Z_
```

The footer is required and its shape is fixed: it is how the next run bounds "new since last time" if `state/runs.jsonl` is ever lost.

## Step 7: commit state

Append to `state/findings.jsonl` and `state/runs.jsonl`, then commit and push **to this skill's own branch** — never to `main`. One commit per run, message `fleet-integrity: <date> (<n> findings, <n> reported)`.

## State files (`state/`, git-backed)

| File | Contents |
|---|---|
| `runs.jsonl` | One record per run: `{run_date, window_start, window_end, prs_open, findings_total, findings_reported, posted, not_checked}`. `posted:false` is a real and expected value. |
| `findings.jsonl` | One record per finding: `{finding_id, repo, pr_number, kind, class, modifiers, first_seen, last_seen, age_band, reported_at, resolved_at, resolution}`. `finding_id` is stable across runs — `<repo>/<pr>/<kind>` — so a finding is announced once and tracked, not re-announced. |
| `reply-log.jsonl` | Per `_shared/thread-feedback.md`. |
| `proposals.jsonl` | Per `_shared/thread-feedback.md`. Nothing here is a CRM change; it is the record of merge/close proposals and their answers. |

Losing `findings.jsonl` costs one noisy run: every open finding reads as new. The footer window in the last post is the fallback baseline.

## Check recipes

`references/checks.md` — the exact `git` and search invocations for every modifier and check above, each with the false-positive it is guarding against. *(Not included in this public showcase.)*
