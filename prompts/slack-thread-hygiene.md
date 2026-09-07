# Slack Thread Hygiene — entry prompt

Run the thread hygiene sweep now. Scheduled for weekdays at 3:00 PM ET. The skill derives its own scan window from the footer of the last digest (Step 3) — don't compute one here or pass one in.

Instructions:

1. **Sync first.** In the acme-skills repo, `git pull` (fast-forward only) so this run uses the latest skill. If the pull fails, say so in the run output, name the last-synced commit, and continue on what you have.
2. **The repo copy is canonical.** Load and follow the repo's `skills/slack-thread-hygiene/SKILL.md` exactly. If an installed copy exists at `~/skills/slack-thread-hygiene/` and differs, replace it with the repo version before running.
3. **Mode comes from config, never from this prompt.** Read `config.yaml` from the skill folder — it is committed, so a fresh clone has it. It currently says `mode: live`, meaning nudge DMs go to the authors and the digest goes to `report_to`. If the file is missing, partial, or unparseable, run as `report_only` instead of guessing; never infer `live` from anything but an explicit `mode: live` in that file.
4. **This may be an unattended run.** Do not stop to ask for confirmation before reading channels or sending the digest. In `live` mode the config *is* the approval — send the nudges within the skill's caps (one DM per person per run, `max_items_per_dm` examples, `min_confidence` and above).
   **Send as `@bot`** — `conversations.open` then `chat.postMessage` with the token in `$SLACK_BOT_TOKEN`, per `contracts/slack-dispatch.md`. This covers the nudge DMs, the digest, and any failure note. `slack_send_message` is the labeled fallback only (italic line naming the failure), never the first choice — and if a nudge can't carry that label, don't send it, report it in the digest instead.
5. **Precision over recall.** Flag only what a reader would call obvious. A run that finds nothing is a valid run — say so plainly rather than lowering the bar to produce output.
6. **Degrade loudly, not silently.** No Slack MCP connector means no sweep (the bot token can only read channels `@bot` is in) — report that and stop. Channels that failed to read, channels skipped on judgment, and any DM that didn't send all belong in the digest and the run summary.
7. Keep logic in the skill, not in this prompt — if behavior needs to change, change `SKILL.md` in the repo via a commit.

Before writing anything that gets posted, read `contracts/slack-format.md`. It is canonical for output format and newer than this skill's own template, so where the two disagree it wins unless the skill's rule is tighter. Run its §10 checklist against the actual draft — in particular, no `**double-asterisk bold**`, no `[markdown](links)`, and no `<@USERID|Name>` pipe-labeled mentions: all three render as visible punctuation through the raw API, and all three have reached a reader.
