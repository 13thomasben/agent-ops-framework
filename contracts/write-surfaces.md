# Shared contract: write surfaces

**Canonical. Every skill in this repo is bound by this file, whether or not it has a reply loop.**

This is the pre-ship gate for *anything a skill writes into a system outside this repo*. It is the companion to two other shared contracts and it outranks both on the one question it exists to answer:

- `_shared/slack-dispatch.md` governs **how** a skill posts to Slack (as `@bot`, never as a person).
- `_shared/thread-feedback.md` governs **when** a skill acts on a reply, and its blast-radius ladder governs *reversibility* and *record ownership*.
- **This file governs who can see the write, and whose name is on it.** Where it conflicts with the ladder in `thread-feedback.md`, this file wins.

## Why this file exists

It was written on 2026-08-19, after an automation wrote 30 comments onto 24 customer-facing Jira tickets over four weeks. The full account lives in the private repo's incident log; the one-line lesson:

> The blast-radius ladder in `thread-feedback.md` asked "is this reversible?" and "whose record is this?" Both answers were reassuring. Nobody asked "who can see it?", so nothing failed — the check passed, in writing, and produced a documented rationale for the exact behaviour that reached customers.

A guardrail that runs the wrong test is more dangerous than no guardrail, because it manufactures confidence. This file adds the two missing tests.

## The four axes

Classify every write on all four. **The most restrictive axis governs the outcome** — a write can be perfectly reversible and still be forbidden because of who sees it.

| Axis | Question | Values |
|---|---|---|
| **1. Reversibility** | If this is wrong, can it be undone? | `additive` · `reversible-in-place` · `destructive` |
| **2. Record ownership** | Whose record does this change? | `automation-owned` · `shared` · `human-owned` |
| **3. Audience** | **Who can see it once written?** | `internal-only` · `internal-plus-participants` · `external-visible` |
| **4. Attribution** | **Whose name appears on it?** | `bot-identity` · `human-identity` |

Axes 1 and 2 came from the original ladder and are unchanged. Axes 3 and 4 are the ones this incident proved were missing.

### Axis 3 — Audience is a property of the destination, not the content

The question is never "is what we're writing sensitive?" It is "**can a non-employee read this surface at all?**" If the answer is yes, the surface is `external-visible` even when a particular write happens to be harmless — because the next write will not be, and the classification is what governs the next write.

`internal-plus-participants` is the trap in the middle: a surface that is internal *by default* but adds external readers per record. A Jira Service Management ticket is exactly this. Its audience depends on who filed it and who was added as a request participant — which means **you cannot classify it from the project alone, and the safe reading is always the widest one.**

### Axis 4 — Attribution: whose name is on it

`_shared/slack-dispatch.md` already got this right for Slack, and the reasoning generalises: *"every Slack WRITE goes through the `@bot` app instead so automation output is not authored by the CEO."*

That rule was never applied anywhere else. All 30 comments in the incident were authored as **the CEO**, because the skill writes through his Atlassian OAuth token, and nothing in the repo said that mattered outside Slack. To the customer they read as the CEO personally sending a status update.

The test to apply: **would the person whose name appears on this write endorse it, unread, every time?** If not, either the write goes out under a bot identity or it doesn't go out.

Where a connector offers no bot identity — the Atlassian MCP does not; it writes as the authenticating user — that connector's writes are `human-identity` and **cannot be used for anything with an `external-visible` audience**, no exceptions and no configuration workaround. That is not a limitation to engineer around; it is the reason the surface is closed.

## The verdict table

Read down. First matching row wins.

| Audience | Attribution | Verdict | Rule |
|---|---|---|---|
| `external-visible` | any | **NEVER** | No skill writes to a surface a customer can read. Not with a visibility flag, not with careful wording, not "just this once" |
| `internal-plus-participants` | `human-identity` | **NEVER** | Cannot establish the audience per record, and cannot disown the write. Both failures at once |
| `internal-plus-participants` | `bot-identity` | **PROPOSE** | Only with a *verified* per-record audience check. Absent that check, treat as `external-visible` |
| `internal-only` | `human-identity` | **PROPOSE** | Colleagues will read it as that person's words. Fine to draft, not to send unattended |
| `internal-only` | `bot-identity` | apply axes 1–2 | Fall through to the `thread-feedback.md` ladder: additive/automation-owned → auto; human-owned → propose |

Two standing clarifications:

- **State is not a message.** Changing a Jira ticket's assignee or status is not shown to the reporter as a communication, so it is `internal-only` even on an `external-visible` project. This is the distinction that let the daily check keep its useful write-backs after losing its comments. Judge the *rendered artefact*, not the API call.
- **"Additive" is not a defence.** It answers axis 1 only. The incident's whole causal chain is a write that was correctly classified as additive and reached customers anyway.

## Surface register

Every destination this repo writes to, pre-classified. **Add a row before writing to a new surface.** An unregistered surface is `external-visible` by default — the default is deliberately the restrictive one.

| Surface | Audience | Attribution | Verdict |
|---|---|---|---|
| **Jira `PROJ` (service desk) — comment** | `internal-plus-participants` (JSM portal; reporter + request participants) | `human-identity` (Atlassian MCP writes as the OAuth user) | **NEVER** |
| **Jira `PROJ` — status transition** | `internal-only` (not rendered as a message) | n/a | Resolved/Done family only |
| **Jira `PROJ` — assignee** | `internal-only` | n/a | auto on unambiguous handoff |
| **Jira `PROJ` — labels** | `internal-only` (not surfaced in the portal request view) | n/a | add-only |
| **Jira `PROJ` — issue create** | `internal-plus-participants` — **the reporter becomes the creator, i.e. us**, so no customer is attached unless one is added | `human-identity` | auto, but never add a customer as reporter or participant |
| **Jira `PROJ` — issue link** | `internal-only` | n/a | auto |
| **Jira `DEV` and other non-JSM projects — comment** | `internal-only` (no portal view) | `human-identity` | auto — the original ladder applies unchanged |
| **Slack channel post (`@bot`)** | `internal-only` (private/internal channels only) | `bot-identity` | auto |
| **Slack DM (`@bot`)** | `internal-only` | `bot-identity` | auto |
| **Slack post as a human user** | `internal-only` | `human-identity` | **NEVER** — see `slack-dispatch.md`; labelled fallback only, and it says so on the post |
| **HubSpot — Note** | `internal-only` (CRM has no customer-facing view) | `human-identity` | auto (additive) |
| **HubSpot — any property, stage, owner, association** | `internal-only` | `human-identity` | **PROPOSE** |
| **Confluence — page the automation owns** | `internal-only` | `human-identity` | auto |
| **Confluence — page a human authored** | `internal-only` | `human-identity` | **PROPOSE** |
| **Repo files (`data/*.csv`, `state/*.jsonl`)** | `internal-only` | `bot-identity` (commit trailer) | auto |
| **Email, calendar, customer portals, anything not listed** | `external-visible` by default | — | **NEVER** without a decision recorded in this file |

## The pre-ship gate

Run this before a new skill ships, and before any change that adds or widens a write. It belongs in `PROCESS.md` as a numbered step; this is the substance behind it.

1. **Enumerate every write.** List each distinct write the skill can make, including ones on paths that rarely execute. *The incident's second-worst finding was a call-intel skill's dedupe comment, which sat outside any reply loop and would never have been caught by a review scoped to the reply contract.*
2. **Classify each on all four axes.** Not "it's additive, fine."
3. **Look up the destination in the register.** Not in the project name, not in your memory of how the tool behaves. If the surface isn't registered, it's `external-visible` and you stop.
4. **Answer the attribution question out loud:** whose name is on this, and would they endorse it unread, every time?
5. **For any `internal-plus-participants` surface, name the per-record audience check** you'll perform — or classify it `external-visible` and move on. An unverified mechanism is not a check. (Jira's `commentVisibility` is the standing example: it accepts only `group`/`role`, has never been verified against this instance, and is **not** an approved mechanism.)
6. **Write the skill's write-surface block into its `SKILL.md`** — one table, the writes and their verdicts, so the next reader doesn't re-derive it.
7. **Name who owns the destination, and check with them.** Not the person who asked for the skill — the person who owns the surface being written to. For the service desk that is the support leads. *Nobody in the incident's authorisation chain owned the customer relationship, which is why the customer-visibility question was never raised by anyone.*

### The one question that would have caught this

> **If this write is wrong, who finds out first — us, or a customer?**

Ask it about every write. On the incident's write-back the honest answer was "a customer," and that answer alone should have closed the path a month earlier.

## Coverage — which skills have a Write surfaces block

Stated plainly rather than left to be discovered, because a gate that looks complete and isn't is the exact failure this file was written about.

**Registered (2026-08-19):** `acme-ticket-daily-check` · `customer-support-scorecard` · `customer-support-scorecard-monthly` · `acme-call-intel` — the four that write into `PROJ`, done first because that is where the incident happened.

**Registered (2026-08-24):** `run-health` — registered at creation, per step 6. Its only writes are a Slack post to `#applied-ai` as `@bot` and its own `state/*.jsonl`; everything else is read-only by design, including the routines and skills it watches.

**Not yet registered:** `bdr-call-coaching` · `bdr-call-coaching-weekly` · `company-scorecard` · `gtm-scorecard` · `hermes-market-intel` · `pre-call-primer` · `slack-thread-hygiene` · `sprint-integrity-readout` · `acme-inbound-leads` · `weekly-pipeline-brief` · `webagent` · `linkedin-watch`.

Their destinations are all classified in the surface register above, and a read of each one's tools puts every write on `internal-only` surfaces — Slack via `@bot`, HubSpot Notes, Confluence pages the automation owns, repo files — with **no writes to any customer-visible surface**. So this is a documentation gap, not a known live exposure. It is still a gap: each block should be written the next time its skill is touched, and until then nobody should assume an unregistered skill has been through the gate.

## What this does not cover

Read access. This file governs writes only. Whether a skill *should* read a surface — a private channel, a customer's ticket — is a separate question this contract does not answer, and one that has not been worked through.

## History

- **2026-08-19** — Created, in response to the incident described above (an automation wrote 30 comments onto 24 customer-facing tickets over four weeks). Adds **audience** and **attribution** as first-class axes alongside the reversibility and record-ownership pair that `thread-feedback.md`'s ladder already had, and moves the gate out of the reply-loop contract so it binds every skill and every write path rather than only replies. The register's default for an unlisted surface is `external-visible`, chosen so the failure mode of forgetting to classify something is a blocked write rather than a customer-visible one.
