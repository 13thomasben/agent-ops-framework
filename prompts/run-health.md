# Run health — entry prompt

Run the run-health sweep now.

Instructions:

1. **Sync first.** In the acme-skills repo, `git pull` (fast-forward only) so this run uses the latest registry. If the pull fails, say so in the run output, name the last-synced commit, and continue on what you have — but say plainly that the registry may be stale, since a stale registry is how this skill goes wrong quietly.
2. **The repo copy is canonical.** Load and follow `skills/run-health/SKILL.md` and its `config.yaml` exactly. If an installed copy exists at `~/skills/run-health/` and differs, replace it with the repo version first.
3. **This is an unattended run.** Do not stop to ask for confirmation before reading channels, reading replies on prior notices (Step 0), or posting the missed-run notice to `#applied-ai`.
   **Post as `@bot`** — Slack Web API `chat.postMessage` with the token in `$SLACK_BOT_TOKEN`, per `contracts/slack-dispatch.md`. `slack_send_message` is the labeled fallback only.
4. **Silence is the expected output.** Most evenings every skill will have run and there is nothing to post. Do not post an all-clear, do not post a summary, do not post a heartbeat. Append the `state/sweeps.jsonl` row and finish. The channel is for things that need acting on.
5. **Report absence, never a guessed cause.** This skill knows whether evidence of a run exists. It does not know why one is missing. Name the skill, the window, and the three places checked. Name a cause only if this run actually observed it, and say how.
6. **A connector you could not use is not a skill that failed.** If the Slack MCP connector is unavailable, mark the skills you could not check as `unchecked` and say so on the notice. Never report a skill as missing because you could not look — that is the worst output this skill can produce, and it destroys trust in every other line.
7. **Never remediate.** This skill does not restart routines, re-run skills, or write to HubSpot, Jira, Confluence or another skill's files. It reports; a human acts. Read-only everywhere except `#applied-ai` and its own `state/`.
8. **Commit state at the end.** `state/sweeps.jsonl`, `state/alerts.jsonl` and `state/reply-log.jsonl`, pushed to `main`. Write the sweep row **even on a clean run** — that row is the only evidence this skill itself is still alive.
9. Keep logic in the skill and cadences in `config.yaml`, not in this prompt. If behavior needs to change, change the repo files via a commit.
