# Acme AI Ops Tracker

Single source of truth for Acme's internal AI work: every agent, routine, platform build, and vendor pilot, plus a weekly update log. **AI systems only** — non-AI workstreams (general company ops) are covered in the weekly updates, not the inventory. Any Claude session with access to this repo reads and writes these files directly — no Google Sheets copy. Edit rules for Claude live in [`CLAUDE.md`](CLAUDE.md).

## Files

| File | What it is |
|---|---|
| `inventory.csv` | The master inventory — one row per agent / routine / platform / vendor pilot. GitHub renders it as a sortable table. *(This showcase ships `inventory.example.csv`, a five-row fictional sample with the real header.)* |
| `daily-log/YYYY-MM-DD.md` | One short entry per day — what moved, what's blocked, decisions, inventory edits. Written by the daily check-in (`prompts/tracker-daily-checkin.md`); feedstock for the weekly brief. |
| `weekly-updates/YYYY-MM-DD.md` | One file per weekly update: Advanced (prior week) → Blocked / needs decision → Targets (upcoming week, prioritized). Built from the week's daily logs by `prompts/tracker-weekly-brief.md`. |
| `briefs/YYYY-MM-DD.html` | The detailed weekly brief as a self-contained HTML page (active-item snapshot, advanced / blocked / targets). Each week's file copies the prior week's as its template. |
| `readouts/` | One-off readouts held for later delivery (e.g. vendor-session syntheses for the CEO) — Slack-markup `.md` + rich-text `-paste.html` pair. |

## inventory.csv columns

| Column | Meaning |
|---|---|
| ID | Stable integer. Never reuse or renumber; new rows take the next number. |
| Tier | `Active` = currently getting attention (above the divider row) · `Dormant` = not being worked — either running untouched on autopilot or a spec going stale (below the divider). |
| Area | Exec / Chief of Staff · Sales & Marketing · Customer Success · Engineering / Product Ops · Knowledge / Ops Infra · Scheduled routines · Data-vendor pilot |
| Name | Short name (skill/routine names verbatim, e.g. `acme-call-intel`) |
| What it does | One- or two-sentence description |
| Type | Skill, Routine, Skill + Routine, Cowork prompt, Platform, Platform (spec), Workflow (spec), Playbook, Vendor setup, Workstream, … |
| Trigger & schedule | When it fires (or "Not built" / "Manual" / "n/a") |
| Routine / Trigger ID | claude.ai routine URL when known |
| Systems touched | Sources and destinations it reads/writes |
| Output surface | Where the output lands (channel, doc, DM, record) |
| Reads / Writes | Read (lowest risk) · Notify (sends messages to people) · Write (modifies records — highest risk) |
| Status | `Built (running)` live on schedule · `Built (automated)` live via routine · `Built (manual)` works, human-triggered · `Built` built, cadence unverified · `Partial` prototype / partly built · `Scoped` designed, not built · `Dropped` consciously abandoned — row stays for history, sinks to the bottom |
| LOE | S = prompt/skill (hours–1 day) · M = multi-step workflow (days–2 weeks) · L = platform (multi-week+) |
| Run-as identity | Whose account it runs under (e.g. the CEO's) |
| Owner | Accountable human |
| Origin chat | Link to the chat/session that built it |
| Notes / known issues | Current state, feedback, blockers, cross-references by ID |
| Review date | ISO date (YYYY-MM-DD) the row was last verified — update whenever you touch the row |

## Conventions

- **Row order carries meaning.** Rows are sorted by attention: most actively worked at the top, untouched at the bottom. A divider row (blank ID, dashes) marks the Active/Dormant line — everything above it is in focus, everything below is on autopilot or going stale. When work starts on a Dormant row, flip its Tier to Active and move it above the divider (and vice versa when something goes quiet).
- The CSV is canonical. Need a spreadsheet view? Generate an xlsx from it on demand — don't maintain a parallel copy.
- Empty cells are intentional: unknown, not zero.
- A few items exist as both a "concept" row and a built routine (e.g. Daily intelligence brief vs the unresponded-slack routines). They stay separate, cross-referenced in Notes.
- Weekly cadence: each new week gets a fresh `weekly-updates/` file; roll the prior week's Targets into the new Advanced/Blocked sections. Keep the update to the CEO (Slack/doc) generated *from* that file.
