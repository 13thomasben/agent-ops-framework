# Scope trace — original ask → what was built → every delta

Standing rule for sponsor-originated systems: deltas are surfaced as decisions
at build time, not discovered later. The original ask was a written v1 build
brief from the sponsor plus a Slack addendum from the service owner (both
internal documents, not included in this public copy).

## Faithful to the letter

Four blocks with the spec's lookbacks and exclusions · emoji-is-not-a-response
enforced structurally (reactions unreadable by the Slack layer) + tested ·
Postgres state store with stable hash IDs built and tested before pull logic ·
email-only delivery, 6:15am ET weekdays, spec's subject-line format · tiers
Blocking/Overdue/Today/Aging with the spec's response windows and scoring
inputs in config · 15-item cap with "N more not shown", Block D uncapped and
compact · deep link + day counter on every item · reply-to-close with reason
"manual" and a labeled-data log · n8n schedule with failure DM to the owner ·
per-run logging with per-block counts and classifier drop rate · rollout
gates and roster active flags per §8.

## Deltas, each decided on 2026-07-27

1. **Auth is Hybrid A+B, not pure Path A.** The brief said "Recommend A if
   Slack and Microsoft 365 admin scopes allow." M365 allows; Slack's platform
   has no admin path to DM content off Enterprise Grid, so Slack is per-user
   OAuth. Decided by the service owner (2026-07-27). Not a drift — the brief's
   own conditional resolving against a platform fact.
2. **"Today" tier = stated deadline of today, for now.** The brief also wants
   "tied to a meeting on today's calendar." That needs `Calendars.Read` and a
   join against events — flagged v1.1 in AUTH.md, not silently dropped.
3. **Jira staleness uses the `updated` field** as the no-movement proxy
   (conservative: any edit resets it). Exact "no status change AND no comment"
   needs changelog reads; revisit if week-1 review shows stale flags missing.
4. **Numbering runs continuously through "Waiting on others"** (§6's example
   restarts at 1 there). Reason: "close 11" must be unambiguous, and pruning
   one's own follow-up list is a legitimate manual close. Template-level
   choice, trivially reversible.
5. **"See full list." dropped from the not-shown line.** v1 has no full-list
   surface to link; printing a dead link violates the working-deep-link rule.
   The line reads "N more not shown." until a surface exists (v2 candidate).
6. **Jira `is_blocking` not auto-detected in v1** (the brief's "linked blocked
   issue" signal). Classifier covers blocking language in A/B/D; C tickets can
   reach Blocking via repeat asks or manual tuning. v1.1: read issue links.
7. **Observable-action closure covers ticket status/reassignment.** The
   brief's other examples (document edited, meeting booked) need Drive/Calendar
   watchers — v2 alongside meeting commitments.
8. **A zero-item morning still sends the all-clear** and DMs the owner the
   anomaly (spec asked only for the alert; suppressing the send would make a
   true all-clear invisible, and since items only leave via logged closure, a
   fake all-clear is detectable in the `runs`/`items` tables in seconds).
9. **Block C skips the ask classifier.** An assigned open ticket is an open
   loop by definition (§2 defines C purely by JQL); classification would add
   cost and a failure mode, not accuracy.

## Unbuilt by design (the brief's own §10)

Task-system push (Asana-vs-Jira decision pending), manager roll-up,
calendar-aware suppression, meeting-transcript commitments.
