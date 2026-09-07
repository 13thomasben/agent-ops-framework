# Thread feedback — reading replies and acting on them

**Every scheduled skill in this repo that posts to Slack must read the replies on its own prior posts and act on them before it produces new output.** A reply is the only feedback channel these skills have. A skill that posts into a channel and never reads back is a broadcast, not an automation — it repeats the same mistake every day and asks the team to correct it every day.

This is the canonical contract. It is the companion to `contracts/slack-dispatch.md`: that file governs **how** a skill writes to Slack, this one governs **what a skill does about what comes back**. Each skill's own `SKILL.md` carries the recipe inline so it stays self-sufficient; this file is the reference for the shared rules, the categories, and the blast-radius limits. **Where a skill's own file and this one disagree, this one wins** — except where the skill's rail is *tighter*, which always survives.

**Skills bound by this contract:**

| Skill | Primary channel | Cadence | Reply lookback |
|---|---|---|---|
| `bdr-call-coaching` | `#bdr-coaching` (`C_EXAMPLE_BDR`) | daily 4:15 PM PT | 7 days |
| `acme-call-intel` | `#sales_prospect-meetings` (id in `data/config.csv`) | weekdays noon, 4 PM, 7 PM ET | 7 days |
| `acme-ticket-daily-check` | `#customer-support-reporting` (`C_EXAMPLE_SUPPORT`) | weekdays 8 AM ET | 5 weekdays |
| `acme-inbound-leads` | `#inbound_leads` (`C_EXAMPLE_LEADS`) | daily 8 AM ET | 14 days |
| `customer-support-scorecard` | `#customer-success` (`C_EXAMPLE_CS`) | weekly Monday | 14 days |
| `sprint-integrity-readout` | `#scrum_process_coach` (`C_EXAMPLE_SCRUM`) | weekly + pre-planning | 21 days |
| `run-health` | `#applied-ai` (`C_EXAMPLE_APPLIED_AI`) | daily 6:30 PM ET | 14 days |
| `fleet-integrity-check` | `#applied-ai_repo_health` (`C_EXAMPLE_REPO_HEALTH`) | weekday mornings | 7 days |

Lookback is deliberately longer than the cadence. Replies arrive a day or two late, on weekends, and after a skipped run.

**That column is the skill's *primary* channel, not the only place it posts.** Nearly every skill here also writes into `#applied-ai` (`C_EXAMPLE_APPLIED_AI`): the Step F suggestion batch, degraded-run notices, and — for `acme-call-intel` — the Gate D ambiguous-call question. `pre-call-primer` posts its primers there as its main surface. Those posts get replies, and a reply there is feedback exactly like a reply in the primary channel. **Step A's sweep runs per channel, over every channel the skill posts into.** See *Every channel the skill posts into* below.

---

## The loop

Run this **first**, before the skill pulls any new data. Outstanding feedback gets resolved before new output goes out, so today's post already reflects yesterday's corrections.

```
discover threads → read replies → drop already-handled → qualify → categorize
    → act (per the blast-radius ladder) → echo in thread → log → commit
```

If there are no unhandled replies, this step produces nothing: no post, no write, no commit. Silence is the correct output.

---

## Step A — Discover the threads

Two paths, always both — plus a third where the skill owns its channel (see *Path 3* below):

1. **The state file.** `state/thread-log.jsonl` in the skill's own directory — one record per post the skill made: `{ts, channel_id, subject, report_date}`. This is the cheap path.
2. **Channel history.** `slack_read_channel` over the lookback window, matching top-level messages on the skill's own **first-line text shapes** (e.g. `"Daily ticket check —"`, `*[Name] — [date]*`). This is the self-healing path: it still finds threads when the state file was lost, a run was skipped, or a post's `ts` never got recorded.

**Every top-level message shape a skill posts must be in both paths.** Not just the main report — alerts, exception messages, and one-off notices too. This is load-bearing, not tidiness: a skill that posts a proposal into a thread the next run cannot find has posted a proposal that can never be approved. It will sit there, expire after 7 days, and the change will silently never happen. If a skill posts it, `thread-log.jsonl` records it and the channel-history matcher knows its shape.

### Path 3 — top-level messages that aren't replies to anything (dedicated channels only)

Both paths above start from a post the skill made, which means **a message that isn't a reply to one of its posts is invisible to the loop.** That is a real gap, not a theoretical one: on 2026-08-19 the CEO posted at top level in `#sales_prospect-meetings` asking how often `acme-call-intel` ran and requesting a cadence change. Every run for the next two days read that channel, found no unhandled thread replies, and correctly reported nothing to do. Someone who doesn't know the loop only reads threads has no way to tell that posting in the channel isn't enough.

**Where a skill owns its delivery channel, it also reads top-level messages there** — anything in the lookback window from a mapped team member that isn't one of the skill's own posts (per the marker table below) and isn't a Slack join/system message. Categorize, act, and log exactly as for a threaded reply, using the message's own `ts` as both `thread_ts` and `reply_ts`. Reply **in a thread under that message**, never at top level.

**The dedicated-channel condition.** This path is only correct where near enough everything in the channel is either the skill's output or someone discussing it — `#sales_prospect-meetings`, `#bdr-coaching`, `#inbound_leads`. It is **wrong** for a general-purpose channel like `#customer-success`, where people hold unrelated conversations all day: there, treating every top-level message as feedback would have the automation reading, categorizing, and potentially acting on things nobody addressed to it. A skill that adds path 3 states in its own `SKILL.md` that its channel qualifies and why. Skills whose channel does not qualify keep two paths, and that is not a defect to be fixed.

**A question gets an answer.** Path 3 surfaces plain questions in a way paths 1 and 2 rarely do — "how often does this run", "why wasn't X in here". If the skill can answer from what it already knows, it answers in the thread in a sentence or two, *and* routes the item if it also implies a change. Routing a question to `#applied-ai` while saying nothing to the person who asked is what let the 8/19 message sit for two days.

**Match on message text, never on author.** Posts before 2026-07-29 were authored by the CEO's account, and any post that took the labeled fallback (see `slack-dispatch.md`) is CEO-authored too. Those threads carry real replies. An author filter silently drops them.

### Every channel the skill posts into

**Paths 1 and 2 run once per channel the skill writes into — not once, against the primary channel.** A skill that posts a question into `#applied-ai` and sweeps only its own delivery channel has asked a question it can never hear the answer to.

**Path 3 does not travel.** It stays in the one channel that meets the dedicated-channel condition above. Paths 1 and 2 are anchored to a post the skill made, so they are safe anywhere; path 3 is anchored to nothing but the channel, so carrying it into a shared channel would have the skill reading conversations nobody addressed to it. Per channel, then: everywhere it posts, paths 1 and 2; in its own dedicated channel only, path 3 as well.

This is not hypothetical. On 2026-08-21 `acme-call-intel` posted a Gate D ambiguous-call notice into `#applied-ai`, asking whether two unmatched calls should be reported. **The CEO answered in the thread 76 minutes later** — the first was a real prospect too early to have a deal created, the second an existing customer's integration project call. That answer was never read by anything. The skill's own file said, and still said three days later, that a channel post "has a thread, so the reply is picked up by the next run's Step 0 like any other feedback." Step 0 swept `#sales_prospect-meetings` and nothing else, so the thread was invisible to every run that followed. The question was asked, answered, and dropped on the floor — and the two calls behind it sat unresolved.

The mechanics are already in place and just weren't used: **`thread-log.jsonl` carries `channel_id` on every record**, precisely so a skill can hold posts in more than one channel. Make it load-bearing — a post into a secondary channel is recorded with that channel's id, and the sweep iterates the distinct `channel_id` values plus every channel the skill's `SKILL.md` names as a posting surface.

**In a shared channel, read only threads under your own posts.** `#applied-ai` is not a dedicated delivery channel — several skills post there and people hold unrelated conversations in it. So:

- **No path 3 there.** Top-level messages in a shared channel are not feedback by default. The dedicated-channel condition is not met and must not be waived.
- **No chaining.** A skill reads threads under the posts *it* made. A reply under `bdr-call-coaching`'s suggestion batch is not `acme-call-intel`'s to act on, even though both posted into the same channel — this is the existing "it does not chain" rule, and a shared channel is exactly where it would otherwise be violated by accident.

**The forwarded-post case.** In `#applied-ai` the most common feedback shape is not a thread reply at all: someone forwards one of the skill's posts out of its own channel and comments above it. Slack renders that as a top-level message carrying an attachment whose permalink points at the original post. **Match on that permalink** — if it resolves to a post this skill made, the message is feedback on that post. This is not path 3 and does not need the dedicated-channel condition: it keys off the skill's own post identity, not off the channel being quiet. Reply in a thread under the forward, and log it with the forwarded post's `ts` as `thread_ts` and the forward's own `ts` as `reply_ts`.

**A question the skill asked deserves a state.** Where a skill posts a question rather than a report — Gate D notices, "should I keep doing X" — it records that it asked, so the same question is not re-posted on the next run before anyone has had time to answer. Without that, a three-runs-a-day skill asks the same question three times a day. `acme-call-intel` posted the *same* ambiguous-call notice for one account twice on 2026-08-21, at 08:09 and again at 15:09, for this reason.

### Skipping the automation's own messages — by marker, not by author

**Skip the bot's own replies** (`U_EXAMPLE_BOT`) inside the thread. Its echoes, corrected re-posts, and proposals are this automation talking to itself — never feedback to act on. Without the skip, an echo that says "Applied to Jira: PROJ-123 → Resolved" reads on the next run as a fresh resolution claim, and the loop feeds on its own output forever.

**The author check alone is not enough.** When the dispatch path fails, every message — including echoes and proposals — goes out under **the CEO's account**, who *is* a mapped team member and therefore passes qualification (Step C). An echo posted on the fallback would be read back next run as a genuine human `data_fix` claim and re-applied. That is the same class of bug as the author filter above, and it bites in exactly the situation where things are already going wrong.

So skip on **either** condition:

- the author is `U_EXAMPLE_BOT`, **or**
- the message body opens with, or contains on its own line, one of the automation's own markers:

| Marker | What it prefixes |
|---|---|
| `*Applied:*` / `Applied to Jira:` | an action echo |
| `*Corrected —` | a corrected re-post |
| `*Proposed HubSpot change*` | a proposal |
| `*Noted:*` | a recorded verdict |
| `_Posted under the CEO's account — the @bot post failed` | the fallback label, present on any fallback message |
| `*Routed:*` | a reply acknowledged and routed to `#applied-ai` without a write — used by read-only skills |
| `*Also came in* ·` | an inbound-leads overflow reply. Was the lower-fit leads carried under a combined post; since 2026-08-21 inbound-leads posts one message per lead, so it now carries only the tail of a single lead whose own message exceeded the length cap. **Still reserved either way** — the pre-change threads it appears on are inside the 14-day lookback |

A skill that adds a new automation-authored message shape adds its marker to this table in the same change. **Reserve these markers.** A human writing "Applied: fixed it" in a thread is vanishingly rare and the cost of ignoring it is one missed reply; the cost of the alternative is an automation acting on its own output.

## Step B — Drop what's already handled

`state/reply-log.jsonl` is the idempotency ledger. One record per reply ever seen:

```json
{"thread_ts":"…","reply_ts":"…","channel_id":"…","subject":"…","report_date":"…",
 "author":"U…","text":"…","category":"…","action_taken":"…","targets":["jira:PROJ-123"],
 "run_date":"…"}
```

**Skip any `reply_ts` already present.** Log replies you take no action on too — that is what marks them seen. Without this, every run re-posts every correction it has ever made and re-writes every ticket it has ever touched.

Belt and braces: every write into an external system also **embeds the reply's Slack permalink** in what it writes (a Jira comment body, a HubSpot note, a Confluence corrections row). Before writing, check whether that permalink is already there and skip if so. The ledger protects against a re-read; the embedded permalink protects against a lost ledger.

**Counter and aggregate edits need the permalink guard too.** A correction that decrements one number and increments another is not self-evidently idempotent the way an appended comment is — re-running it silently doubles the damage. Any correction that adjusts a count, total, or rolling field must carry the reply permalink in a note or audit row alongside it, and check for that permalink before applying. Where the aggregate can be re-derived from an append-only log (as `competitors.csv` can from `mentions_log.csv`), **re-derive rather than adjust** — recomputation is idempotent by construction.

## Step C — Qualify the reply

A reply is actionable only when **all three** hold:

- it is in a thread under a post this skill made, and
- the author is a mapped team member (in the skill's user map — not the customer, not a bot, not an unrecognized account), **and it is not one of the automation's own messages per Step A's marker table**, and
- it references something the skill can act on: a specific record key, a named entity, a metric in the post, or a change to how the skill works.

Everything else gets logged with `category: none` and no action.

## Step D — Categorize

| Category | What it is | Where it goes |
|---|---|---|
| **`report_correction`** | The post itself was wrong — a miscount, a misread disposition, a wrong attribution, a wrong name. The source system is fine. | Corrected re-post in the thread (Step E) |
| **`data_fix`** | The *source record* is wrong or stale — a ticket that's actually resolved, a handoff that already happened, a deal field that's out of date, an account miscategorized. | Write it back to the system of record, per the blast-radius ladder |
| **`product_or_architecture`** | A change to how the skill (or the product) should work going forward — add a metric, stop counting X, change the format, change the cadence, a feature idea, a workflow redesign. | Batched to `#applied-ai` (Step F) |
| **`none`** | "nice", thanks, emoji, banter, a question the post already answered. | Log only |

**Every skill implements all four**, including `report_correction` — a skill that lists the category but has no step that acts on it will silently drop the most common kind of feedback it gets. The Step E recipe below is the default implementation; a skill only needs its own wording where the correction touches something skill-specific (a published page, a tracker file).

**A reply can be more than one category.** *"Those 3 AM dials are a dialer glitch, and can you flag outliers going forward?"* is a `data_fix` **and** a `product_or_architecture`. Handle both halves.

**When a reply could be either a `report_correction` or a `product_or_architecture`, treat it as `product_or_architecture`.** Re-posting a "corrected" report on a guess puts wrong numbers in the channel under the bot's name; routing it to `#applied-ai` costs one day. When it could be a `data_fix` or a `product_or_architecture`, same rule — the ambiguous case never writes to a system of record.

**Examples in a skill's category table must be actionable by that skill.** If a skill's HubSpot scope is three company fields, do not illustrate `data_fix` with a duplicate-account merge — that isn't a `data_fix` for that skill, it's a `product_or_architecture` item, and listing it in the wrong row invites an improvised write.

---

## Step E — Act: the blast-radius ladder

> **Read `_shared/write-surfaces.md` first.** This ladder reasons about *reversibility* and *who owns the record*. It does **not** reason about who can see the write or whose name is on it, and on 2026-08-19 that gap cost 30 customer-visible Jira comments across 24 tickets. Those two axes — **audience** and **attribution** — live in `write-surfaces.md`, which is canonical for them and **wins wherever it is more restrictive than this table.** A write this ladder puts on the **auto** rung is still forbidden if that file says the surface is customer-visible.

This is the load-bearing part of the contract. **Auto** means the skill just does it. **Propose** means the skill posts what it *would* do and waits for a human yes. The line is drawn at reversibility and at who owns the record.

| Target | Action | Mode | Rails |
|---|---|---|---|
| **Slack — this thread** | corrected re-post, echo, proposal | **auto** | Reply under the original; never `chat.update` the original away |
| **Jira — service desk (`PROJ`)** | add a comment | **never** | A comment on a JSM ticket is published to the reporting customer. **No skill in this repo writes one.** See the service-desk rule below |
| **Jira — non-portal (`DEV` and other non-JSM projects)** | add a comment | **auto** | For every qualifying reply. Verbatim quote + author + date + permalink. There is no customer portal view on these projects |
| **Jira** | reassign | **auto** | Only on an unambiguous handoff, and only when the name resolves to exactly one accountId in the user map |
| **Jira** | transition | **auto** | **Resolved / Done family only.** Never reopen, never Won't Do / Cancelled |
| **Jira** | priority, labels, due dates, others' comments, deletion | **never** | Not in scope for any skill. A reply asking for one becomes `product_or_architecture` |
| **Repo tracker files** (`data/*.csv`, `*.jsonl`) | fix or append a row | **auto** | Version-controlled and reversible by design. Commit per the skill's own push rule |
| **A page or table the automation itself authors and owns** (a weekly scorecard page, the quarter trends table) | append a *Corrections* block; update a row the skill itself wrote | **auto** | See *automation-owned artifacts* below |
| **A Confluence page a human authored** (Methodology, hub pages) | anything | **PROPOSE** | Not ours to edit, however obvious the fix looks |
| **HubSpot** | add a Note / log an activity | **auto** | Additive annotation. Creates a new object, changes nothing existing |
| **HubSpot** | any property, stage, owner, lifecycle, association, or record edit | **PROPOSE** | See the protocol below. The skill never writes these on its own |
| **Any other connected system** (email, calendar, HubSpot workflows) | anything | **PROPOSE** | Default-deny. New surfaces start on the propose path and only graduate by an explicit decision recorded here |

**The rule underneath the table:** a skill acts on its own when the action is *additive* (a comment, a note, an appended row), *reversible inside a system the automation already owns* (Slack threads, Jira status within the Resolved family, git-tracked files), or *a correction to an artifact the automation itself produced*. Anything that **overwrites a record a human owns** stops and asks. That split is deliberate — it is the standing "guard in the skill, human owns the data fix" rule, narrowed rather than abandoned: the skill now does the work of *finding and drafting* the fix, and a person only has to say yes.

### Rule: no skill writes a comment on a service-desk ticket

**"Additive" is not the same as "internal."** `PROJ` is a Jira Service Management project. A comment written there through the Atlassian MCP lands on the **public reply channel** — Jira's "Reply to customer" — so the reporter and every request participant is emailed it and sees it in the portal. A write-back comment is additive and reversible in the ladder's sense, and still reaches a customer as what reads like an official status update from Acme.

This is not hypothetical, and it was not a single slip. On 2026-08-17 `acme-ticket-daily-check` mirrored a Slack reply reading "This has been resolved. Did already contact client on status update" into a service-desk ticket; the reporter at a customer replied "Not resolved!!" seventeen minutes later. **The 2026-08-19 audit found that the same write-back had run on 24 service-desk tickets** between 2026-07-23 and 2026-08-17 (full list in that skill's CHANGELOG entry) — that ticket was the one a customer answered, not the only one a customer received.

**The rule, repo-wide, effective 2026-08-19:** no skill bound by this contract writes a Jira comment on `PROJ` or any other service-desk project, for any reason, on any rung — not a thread-feedback write-back, not a dedupe annotation on an existing ticket, not a correction to a ticket the automation itself filed. There is no ambiguity path that ends in a comment: a `data_fix` that cannot be expressed as a reassign or a Resolved/Done transition is **acknowledged in the Slack thread and left unwritten**. Ticket *state* changes are unaffected — the reporter is never shown a transition or a reassignment as a message.

**Do not reintroduce this behind a visibility parameter.** Jira's per-comment visibility restriction is the obvious-looking workaround and it is **not a substitute**: the Atlassian MCP's comment tool exposes only role/group `commentVisibility`, not JSM's native internal-note (`jsdPublic`) flag, and it is unverified against this instance. The CEO's call on 2026-08-19 was to retire the whole class of "the automation said something to a customer" rather than narrow it. Reversing that needs an explicit decision recorded in this file, and evidence from someone who can see a ticket in the customer portal.

Status of the three skills that were flagged as unaudited on 2026-08-19, now audited: `customer-support-scorecard` had Jira comments on its `data_fix` rung and **no longer does**. `acme-call-intel` had them on both its `data_fix` rung and its Step 5 dedupe path and **no longer does**. `customer-support-scorecard-monthly` turned out to make **no Jira writes at all** — it has no reply loop — and is now explicitly read-only against Jira.

None of this restricts comments on **`DEV`** or other non-service-desk projects, where there is no customer-facing portal view.

### Automation-owned artifacts

A weekly scorecard page and the quarter trends table are written by the skill, every week, with no human author. Correcting a row the skill itself wrote last Monday is the same class of act as correcting one of its own tracker files — not an overwrite of someone's work. Those stay **auto**, with two conditions:

- **A published figure is never silently replaced.** The corrected value can land in the table, but the change is also recorded in an appended, dated `## Corrections` block naming what changed, from → to, who flagged it, and the Slack permalink. Someone who read the old number has to be able to see that it moved and why.
- **Ownership is per-artifact, not per-system.** Confluence is not blanket-auto: the Methodology page, hub pages, and anything a person wrote are on the propose path like everything else. The carve-out covers only pages and tables this skill created and maintains.

### `report_correction` — fix and re-post in the thread

Rebuild the affected part of the post and reply **in the thread the feedback was left in** — `thread_ts` = the `ts` of the post being corrected, which is very often an *earlier* post, not today's. Open with one line naming what changed and who flagged it:

```
*Corrected — [what changed], per <@REPLIER_ID>.*
[the corrected content]
```

The same applies to every echo and proposal: they thread onto the post the reply came from. A skill that echoes onto today's new post puts the answer somewhere the person who asked will not look, and orphans the proposal from the conversation that produced it.

Leave the original message alone. The thread carries the history of what was wrong; a silent `chat.update` erases the fact that the automation got it wrong, which is exactly the record the team needs to see.

### The HubSpot propose/approve protocol

When a reply reveals a CRM record is wrong, the skill does **not** write. It posts one proposal per record, in the same thread:

```
*Proposed HubSpot change* — <@OWNER_ID>
[Record type] [Record name] (<link|open in HubSpot>)
  [field]: `[current value]` → `[proposed value]`
Because: "[the reply quote]" — <@AUTHOR_ID>, [date]
Reply *approved* in this thread and I'll apply it on the next run. No reply, no change.
```

Then:

- **Approval must be explicit and from a mapped team member.** "approved", "yes do it", "go ahead", "confirmed" — a clear affirmative naming this proposal or replying directly beneath it. A 👍 reaction does not count; reactions are not read. Silence does not count. Anything hedged ("probably", "I think so") does not count.
- **The approval is itself a reply** — the next run picks it up through the same loop, applies the change, and echoes it. That means a proposed change lands one cadence later. That delay is the feature.
- **Post the proposal only into a thread the next run can find**, per Step A. A proposal in an undiscoverable thread is a change that will never happen.
- **Log the proposal** in `state/proposals.jsonl`: `{proposal_id, thread_ts, reply_ts, record_type, record_id, field, from, to, proposed_at, status}` with `status` in `proposed` / `approved` / `applied` / `rejected` / `expired`. Never post the same proposal twice — check this file first. Move `status` to `applied` in the same run the write lands, so an approval read twice cannot apply twice.
- **Proposals expire after 7 days** with no answer. Mark `expired`, say so once in the thread, and drop it. Never re-propose the same change automatically; if the condition recurs it will be re-detected from fresh evidence anyway.
- **A rejection is data.** "no, that's right as-is" → mark `rejected` and, where the skill has a verdict store (e.g. `bdr-call-coaching`'s `state/account-verdicts.jsonl`), record the verdict so the same thing is never proposed again.

### Echo every applied action, immediately

The moment a write lands, reply in the same thread saying what happened:

```
*Applied:* PROJ-123 → Resolved (per <@U_EXAMPLE>) · comment logged on PROJ-125 · competitors.csv row corrected.
```

Non-negotiable. The team must be able to see what the automation did to their systems at the moment it did it, without going and looking. An action taken silently is indistinguishable from a bug.

If a write **failed**, echo that too, naming the system and the error. Never retry destructively, never fail silently.

### The write-back marker

Every comment a skill writes into another system on a reply's behalf carries a fixed marker so it can be recognized later — by the idempotency check, and by any metric that must not count it:

```
logged by [skill-name] · [thread permalink]
```

**A skill's own write-back comment is not a human response.** Any responsiveness or engagement metric — first-response time, no-response counts, last-touched — must exclude comments carrying this marker. Counting them makes the metric measure the automation instead of the team, and quietly improves every period the loop gets busier.

### Tally lines

Skills that report what the loop did ("Yesterday's thread → Jira: N comments · M reassigned · K resolved") **omit the line entirely when every number is zero.** A zero tally is an all-clear message, and every skill here has a stay-silent-when-there's-nothing rule that an all-clear line contradicts.

### Caps and hard rails

- **10 write actions per run, per skill.** Hitting the cap means something is wrong — a mis-parse, a runaway thread, a state file that got wiped. Stop, apply nothing further, and say so in the thread instead.
- **Ambiguity always degrades one rung.** Unsure between two records → comment only. Unsure whether a handoff is a handoff → comment only. Unsure at all about a CRM field → propose, don't write.
- **Never act on a reply from outside the user map**, and never act on a message matching Step A's marker table.
- **Never delete anything**, in any system, ever.
- **A correction changes the report and, where allowed, the record — it never changes a principle.** A reply asking the skill to violate a stated principle in its own SKILL.md (coach-not-cop, the list-quality rule, less-is-more, one-call-one-report) is a `product_or_architecture` item and is routed, not obeyed. Say so plainly in the `#applied-ai` message.
- **The reassign rail needs pinned accountIds.** A skill that reassigns in Jira must carry a Jira accountId per person in its user map, resolved once via `lookupJiraAccountId` and pinned into its SKILL.md. Until those are pinned, the unambiguous-resolution condition can never be satisfied and reassignment correctly degrades to **no write plus a thread note** — which is safe, but silent. (It used to degrade to comment-only; that path is gone on service-desk projects as of 2026-08-19.) Pin them or say in the file that reassign is disabled.

---

## Step F — Route product and architecture changes to `#applied-ai`

Everything categorized `product_or_architecture` goes to `#applied-ai` (`C_EXAMPLE_APPLIED_AI` — **private**, `@bot` must be invited).

- **One message per run, per skill**, covering every such suggestion collected that run. Never one message per suggestion. No suggestions, no message.
- **Tag the Owner** (`<@U_EXAMPLE_OWNER>`) — they own the skills and the build queue.
- **Add the CEO** (`<@U_EXAMPLE_CEO>`) **only when the item is a scope change** (below). The CEO is the sponsor; they see the ones that change what a system is for, not the ones that change how it's implemented.

**A suggestion is a scope change when it:**

- changes what the skill is *for*, or who it serves;
- adds, removes, or redirects a delivery surface or audience;
- conflicts with a stated principle in the skill's own SKILL.md;
- changes what gets written automatically to a system of record (i.e. moves something up the blast-radius ladder);
- changes cadence, schedule, or the lookback window; or
- is a product change to Acme's own product rather than to a skill.

Everything else — a new metric, a format tweak, a threshold, a wording change, a new field on a tracker — is an implementation change. The Owner only.

**Format:**

```
*[Skill name] — thread suggestions, [date]*

1. "[verbatim quote]" — <@AUTHOR_ID>, on [which post], [date]
   *Route:* [which step or reference file changes, and how]
   *Trade-off:* [only if there is one — including any principle it collides with]
   *Scope change:* [yes + why, or omit the line entirely]
```

**The route is the point of the message.** A suggestion forwarded without a proposed implementation just moves the thinking to someone else. Say which part of the skill would change and how. When a suggestion collides with an existing principle, say that instead of quietly proposing it — the collision is the most useful thing in the message.

---

## Step G — Log and commit

Append to `state/reply-log.jsonl` (every reply, actioned or not), `state/proposals.jsonl` (any proposal raised, approved, applied, rejected, or expired), and the skill's own trackers. Commit and push at the end of the run per the skill's push rule — for git-backed skills, **a `git commit` is the write**, and anything uncommitted is lost when the next run starts from a fresh checkout.

**Never write state that claims an action happened when it didn't.** If both Slack paths failed, or a Jira write errored, the log records the failure, not the intent. The next run needs to be able to retry.

---

## State file conventions

Every skill bound by this contract keeps these under `state/`:

| File | Contents | Purpose |
|---|---|---|
| `thread-log.jsonl` | `{ts, channel_id, subject, report_date}` per post — **every** top-level shape, alerts included | cheap thread discovery |
| `reply-log.jsonl` | one record per reply seen, with `category` and `action_taken` | idempotency ledger |
| `proposals.jsonl` | one record per proposed CRM change, with `status` | the propose/approve queue |

`subject` identifies which post it is — the BDR's name, the alert type, the week. A skill reads back only fields it writes; if a step needs a field, the posting step writes it.

**`acme-call-intel` differs, deliberately.** It keeps these in its existing `data/` directory and uses underscore names (`reply_log.jsonl`, `proposals.jsonl`) to match its siblings there (`processed_calls.jsonl`, `team_slack_ids.csv`). It also has no `thread-log.jsonl`: thread discovery comes from the `slack_ts` already stored on each `processed_calls.jsonl` line (older lines carry only `slack_permalink` — the `p1234567890123456` fragment is the parent `ts` with the decimal removed). It is the first skill to implement **path 3**; `#sales_prospect-meetings` is a dedicated delivery channel, so a top-level message there is feedback by default.

**A recorded `ts` is only as good as the post it points at.** If a report was ever split by Slack's ~4,000-character boundary (see `slack-dispatch.md`), the `ts` returned by `chat.postMessage` belongs to the *tail* fragment — so the anchor points at a message nobody replies to, and path 2's first-line matcher can't recognise the fragment either. Seven of `acme-call-intel`'s reports were anchored this way before 2026-08-21. Skills that record a thread anchor must keep their posts under the split boundary, or verify after posting which fragment they're holding.

**A state file that doesn't exist yet is an empty one.** These files are created on first write, so a skill's first run after this contract lands will find none of them. Treat a missing file as zero records and carry on — do not error, and do not treat "no thread log" as "no threads" (the channel-history path is there for exactly that first run).

Losing `reply-log.jsonl` is not catastrophic but it is loud: the next run re-posts old corrections. Losing `proposals.jsonl` is worse — a proposal could be raised twice, or an approval applied twice. Both are committed to git for exactly that reason.

---

## What this contract does not do

- **It does not read reactions.** Only message replies. A 👍 is not an approval and not a signal.
- **It does not read DMs.** Feedback lives in the thread, where the rest of the team can see it.
- **It does not act on customer replies.** Only mapped internal team members.
- **It does not chain.** A skill acts on replies to *its own* posts only. `acme-ticket-daily-check` does not act on something said in `#bdr-coaching`. Note the unit is the **post, not the channel** — in a shared channel like `#applied-ai` several skills post side by side, and a reply under a sibling's message is still not yours.
- **It does not learn silently.** Every behavior change goes through `#applied-ai` and a human editing a SKILL.md. Nothing in this loop rewrites a skill's own instructions.

---

## Changelog

- **2026-08-24** — The sweep runs per channel, over every channel a skill posts into. The binding table's channel column was read as *the* channel rather than the *primary* one, so a skill that posted a question into `#applied-ai` swept only its delivery channel and never saw the answer. `acme-call-intel` asked the CEO on 2026-08-21 whether two unmatched calls were in scope; the answer came in the thread 76 minutes later and nothing ever read it, while the skill's own file claimed such replies were "picked up by the next run's Step 0 like any other feedback." Added: the per-channel sweep, the shared-channel restrictions (no path 3, and the no-chaining rule restated as post-scoped rather than channel-scoped), the forwarded-post permalink matcher for the way feedback actually arrives in `#applied-ai`, and a requirement that a skill which posts a *question* records that it asked — the same notice went out twice in one day for want of that.
- **2026-08-19** — Added the service-desk warning to the blast-radius ladder. A Jira comment is additive, which the ladder treated as sufficient for the auto rung, but on a JSM project it is also customer-visible — `acme-ticket-daily-check` put an internal "this has been resolved" note in front of a customer on 2026-08-17 and got "Not resolved!!" back. That skill dropped its comment rung entirely (the CEO, 2026-08-19); the three sibling skills that also write into the service desk are flagged as unaudited rather than changed. The lesson for the contract itself: *additive* and *internal* are different properties, and the ladder only ever reasoned about the first.
- **2026-07-30 (b)** — Six fixes from an adversarial review of the first version. The author-only self-skip missed the case that matters most: on the labeled fallback, echoes and proposals are authored by the CEO, a mapped team member, so the next run would read its own "Applied to Jira" echo back as a fresh human claim — replaced with a marker-based skip. Echo/correction threading pinned to the post the feedback was left on, not today's. The ladder's blanket Confluence propose-only row contradicted the scorecard's own weekly trends write — carved out as *automation-owned artifacts*, with human-authored pages still propose-only. Added: every postable message shape must be discoverable (a proposal in a thread the next run can't find silently expires), the write-back marker is pinned and excluded from responsiveness metrics, zero-valued tally lines are omitted, counter edits need the permalink guard or re-derivation, and the reassign rail's pinned-accountId prerequisite is stated.
- **2026-07-30** — First version. Generalizes the reply loop that `bdr-call-coaching` (Step 0) and `acme-ticket-daily-check` (Steps 1b/1c) each grew independently, and extends it to `customer-support-scorecard` and `acme-call-intel`. Adds the blast-radius ladder, the HubSpot propose/approve protocol, and the `#applied-ai` routing rule with the Owner as owner and the CEO on scope changes.
