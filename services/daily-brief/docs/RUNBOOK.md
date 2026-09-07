# Stand-up runbook

Twelve steps, worked top to bottom. Steps 1–4 are the box; 5–8 are credentials
(the only part needing anyone besides the service owner — step 5's one
admin-consent click); 9–12 are rollout. Budget an afternoon for 1–8.

## 1. Box
Any small VPS (Hetzner CX22 / DigitalOcean basic / Railway) with Docker.
~$5–8/mo. Ubuntu 24.04 + `curl -fsSL https://get.docker.com | sh`.

## 2. DNS
A record `ops.acme.example.com` → box IP (needed for Slack OAuth redirect + n8n
webhooks; Caddy gets the certificate automatically).

## 3. Clone + env
```bash
git clone <this repo> daily-brief && cd daily-brief
cp .env.example .env && chmod 600 .env   # fill as steps 5–7 produce values
cp config/roster.example.yaml config/roster.yaml   # fill with real people
```
Generate `POSTGRES_PASSWORD` and `SERVICE_TOKEN`: `openssl rand -hex 24`.

## 4. Up
```bash
docker compose --profile edge up -d
docker compose exec brief python -c "import brief; print('service alive')"
```

## 5. Microsoft 365 (AUTH.md, Path A)
Entra app registration → application permissions `Mail.Read` + `Mail.Send` →
**admin consent** (Global Admin, one click) → client secret → `.env`
(`M365_TENANT_ID`, `M365_CLIENT_ID`, `M365_CLIENT_SECRET`). Then the
`brief-scope` access policy and the `brief@acme.example.com` shared mailbox —
PowerShell block is in AUTH.md. Verify:
`docker compose exec brief python -c "from brief.credentials import m365_token; m365_token(); print('graph ok')"`

## 6. Jira
Service account API token → `.env`. Fill each roster `jira_account_id`:
```bash
curl -su "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/user/search?query=sponsor@acme.example.com" | jq '.[0].accountId'
```

## 7. Slack app
api.slack.com/apps → Create from manifest → paste
`config/slack-app-manifest.yaml` (fix the redirect URL to your `N8N_HOST`) →
install to workspace → `.env`: `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`,
`SLACK_BOT_TOKEN`.

## 8. n8n
`https://ops.acme.example.com` → create owner account → import the three
`n8n/*.json` workflows → open "Slack OAuth redirect", copy its production
webhook URL into the Slack app's redirect URLs → activate all three.
Schedules fire in `America/New_York` (set in compose + workflow settings).

## 9. Consent per user (rollout order!)
Send the consent link from AUTH.md. Week 1: the sponsor only. The redirect
page says "Connected" and the token lands in the `credentials` table.

## 10. Dry run against the service owner
```bash
docker compose exec brief python -m brief.run --user owner --dry-run
```
Read `out/<date>-owner.html`. Iterate `prompts/ask_classifier.md` and
`config/weights.yaml` until your own brief reads true. Log changes in
TUNING-LOG.md.

## 11. Sponsor live
Roster: `sponsor.active: true`. Restart `brief`. Next 6:15am is their first
brief. Owner + sponsor review every morning of week 1 against what they
actually owed (target: <2 in 10 wrong).

## 12. Watch it
- `runs` table: per-block counts, classifier drop rate, closures, errors.
- Failure alert: service DMs the owner on a user-run failure; n8n error
  workflow DMs the owner if the service itself is unreachable.
- Zero-items-after-nonzero anomaly: DM to the owner (all-clear still sends —
  closures are all logged with reasons, so verify in 30 seconds).

## Failure playbook
| Symptom | Look at |
|---|---|
| No 6:15 email | n8n executions → `docker compose logs brief` → `runs.error` |
| Slack items missing for one user | their `credentials` row (re-consent if revoked) |
| Graph 403 | access policy group membership; secret expiry (2y default) |
| Classifier junk | drop rate in `runs.counts`; tune prompt, not thresholds first |

## Rotation points (if the box is ever compromised)
Entra client secret · Slack app reinstall (invalidates all user tokens) ·
Jira API token · `SERVICE_TOKEN` + `POSTGRES_PASSWORD` in `.env`.
