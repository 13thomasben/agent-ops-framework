# Claude instructions — Acme AI Ops Tracker

You are working in the canonical tracker for Acme's internal AI work. Multiple Claude accounts (the Owner's, the CEO's, cloud Cowork sessions) read and write these files. Follow these rules exactly so edits from different sessions stay consistent.

## Before any edit

1. Pull latest (`git pull`) before reading or writing. Never edit from a stale copy.
2. Read `README.md` for column definitions and status vocabulary. Use only the existing vocabulary for Status, LOE, Reads/Writes, and Area unless the human asks to extend it.

## Editing inventory.csv

- One row per system. Match rows by **ID**, not by name — row ORDER is meaningful (attention rank) and changes over time.
- **Tier + divider:** rows are sorted most-active (top) to untouched (bottom). The divider row (blank ID, dash-filled) separates `Tier=Active` from `Tier=Dormant`. Keep the divider; skip rows with a blank ID when parsing. Moving a row across the divider and flipping its Tier must happen together. New Active rows slot above the divider at the right attention rank; new backlog ideas go below it with `Tier=Dormant`.
- Never renumber, reuse, or delete IDs — including for items that die. Abandoning something = set Status to `Dropped`, note why, move the row to the very bottom. New rows take the next integer ID.
- **Scope: AI systems only** (agents, routines, platforms, vendor pilots). Non-AI workstreams — general company ops — belong in the weekly-updates files, never as inventory rows. (One early ID was a non-AI workstream, removed 2026-07-21 as out of scope; it stays retired — do not reuse.)
- When you change anything in a row, set **Review date** to today (YYYY-MM-DD).
- Status changes: update Status AND describe the why in Notes (short, dated like `7/21:` when useful).
- Keep cell text single-line (no newlines inside fields). Quote naturally via CSV rules; preserve the header row exactly.
- Do not reformat the whole file (no re-quoting every field, no column changes) — keep diffs to the rows you actually touched.

## The cadence — daily feeds weekly

- **Daily check-in** (`prompts/tracker-daily-checkin.md`): updates inventory rows that moved and appends `daily-log/YYYY-MM-DD.md`. One entry per day, never edited after the fact; "no movement" days still get an entry.
- **Weekly brief** (`prompts/tracker-weekly-brief.md`): reads the week's daily logs + inventory + git log, then produces three things together — `weekly-updates/YYYY-MM-DD.md`, `briefs/YYYY-MM-DD.html` (self-contained page, copy the prior week's file as template), and a Slack summary delivered in chat.

## Weekly updates

- One file per week: `weekly-updates/YYYY-MM-DD.md` (date = the day the update is prepared). Never overwrite a prior week.
- Structure: `## Advanced` (what moved last week) → `## Blocked — waiting on others` → `## Targets` (upcoming week, numbered by priority). Keep any standing sections the human uses (e.g. the vendor trial benchmark).
- **Blocked vs Target rule (the Owner's):** Blocked holds ONLY items whose unblock is owned by someone else (the data vendor, the CEO, another team). If the Owner is the POC for the unblock, it is a Target, never a Blocked item.
- **Vendor grouping:** within every section (and the brief), group data-vendor-pilot items together and flag them (`[VENDOR]` in markdown, the small VENDOR chip in HTML) — unflagged items are the Owner's own work.
- The trimmed Slack summary is part of the weekly status: save the as-sent copy to `briefs/YYYY-MM-DD-slack.md` and commit it with the week's files.
- Build Advanced/Blocked from the week's `daily-log/` entries plus the prior week's Targets. Cross-check statuses against `inventory.csv` and `git log`, and update inventory + weekly file together.

## Commits

- Small, scoped commits. Message format: `tracker: <what changed>` — e.g. `tracker: call-intel Sheets issue resolved, review dates 8/03` or `tracker: add weekly update 2026-07-28`.
- Commit inventory.csv changes and the related weekly-update file together when they describe the same week.
- If a push is rejected (someone else pushed first), pull/rebase and re-apply your row edits — never force-push.

## Don'ts

- Don't create parallel copies (no xlsx committed here, no Google Sheets export as source of truth).
- Don't log routine run history here — the tracker is inventory + weekly narrative, not a run log; runs log wherever each skill's own convention says.
- Don't remove or rewrite prior weekly-update files, even to fix errors; correct forward in the current week's file.
