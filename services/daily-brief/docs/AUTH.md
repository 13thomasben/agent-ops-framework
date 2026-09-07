# Auth decision — checklist item 2 (the June gate)

**Decided 2026-07-27 by the service owner: Hybrid A+B.** This resolves the
per-user auth question flagged as a blocker in the earlier ops plan. It gated
everything; it no longer does.

## The decision in three lines

1. **Microsoft 365 → Path A.** One Entra app registration with application
   permissions, one admin-consent click, restricted to roster mailboxes by an
   application access policy. Scales to the whole team with zero per-user steps.
2. **Slack → Path B, and this is forced, not chosen.** On a standard
   (non-Enterprise Grid) Slack plan, no workspace-level, admin, or bot token can
   read a user's DMs — Slack only exposes a DM to a token whose owner is a
   member of that conversation. The Discovery API that would enable Path A is
   Enterprise Grid only. So each user grants a one-time OAuth consent that
   issues a user token. This matches the rollout cadence anyway: consent is
   part of onboarding each cohort.
3. **Jira → service account.** One API token with browse permission on the
   in-scope project(s). No per-user anything.

The brief's own language was "Recommend A if Slack and Microsoft 365 admin
scopes allow." They allow for M365 and do not exist for Slack. Hybrid is
therefore the fastest rollout that is actually possible.

## Microsoft 365 (Path A)

**App registration** (Entra admin center → App registrations → New):

- Name: `Acme Accountability Brief`
- Supported account types: this org only
- API permissions (Microsoft Graph, **Application** type):
  - `Mail.Read` — read roster mailboxes (blocks A and D, closure detection,
    reply-to-close inbox)
  - `Mail.Send` — send the brief from the shared mailbox
  - (v1.1, optional) `Calendars.Read` — "Today" tier meeting linkage
- Click **Grant admin consent** (requires a Global Admin — if that is not
  the service owner, send them this section; it is one click after review).
- Create a **client secret**; record Tenant ID, Client ID, secret → `.env`.

**Scope the app to roster mailboxes only** (this is what makes Path A
defensible — the app cannot read anyone else, in PowerShell / Exchange Online):

```powershell
New-DistributionGroup -Name "brief-scope" -Type Security -Members sponsor, lead, owner, brief
New-ApplicationAccessPolicy -AppId <CLIENT_ID> -PolicyScopeGroupId brief-scope@acme.example.com `
  -AccessRight RestrictAccess -Description "Accountability Brief reads/sends only these mailboxes"
Test-ApplicationAccessPolicy -AppId <CLIENT_ID> -Identity sponsor@acme.example.com       # expect: Granted
Test-ApplicationAccessPolicy -AppId <CLIENT_ID> -Identity someone-else@acme.example.com  # expect: Denied
```

Add each rollout cohort to `brief-scope` as they onboard.

**Shared mailbox**: create `brief@acme.example.com` (Exchange admin → shared
mailbox, no license needed). It sends every brief and receives reply-to-close.
Add it to `brief-scope`.

**Token flow**: client-credentials grant against
`https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token`, scope
`https://graph.microsoft.com/.default`. Implemented in `brief/credentials.py`;
tokens are cached in memory, never stored.

## Slack (Path B)

**One Slack app, two token types** — create from `config/slack-app-manifest.yaml`
at api.slack.com/apps → Create New App → From an app manifest:

- **User tokens** (`xoxp-`, one per roster user, via OAuth consent):
  `channels:history`, `groups:history`, `im:history`, `mpim:history`,
  `search:read`, `users:read` — everything blocks B and D need, including the
  user's own DMs and mentions, seen exactly as that user sees them.
- **Bot token** (`xoxb-`, one for the workspace): `chat:write`, `im:write` —
  used only for failure/anomaly DMs to the service owner. Bots can DM; they
  cannot read your DMs. The two directions are not symmetric, which is the
  whole reason Path B exists.

**Consent flow**: user clicks
`https://slack.com/oauth/v2/authorize?client_id=<ID>&user_scope=channels:history,groups:history,im:history,mpim:history,search:read,users:read&redirect_uri=<REDIRECT>`
→ Slack redirects to the n8n webhook (`n8n/workflow-slack-oauth.json`) → n8n
forwards the code to the service (`POST /oauth/slack/exchange`) → service
exchanges it and stores the user token in the `credentials` table. The user
sees "Connected" and is done forever (Slack user tokens do not expire unless
token rotation is enabled — leave it off for v1).

Onboarding step per person: send them the consent link. That is the entire
per-user cost of Path B.

## Jira (service account)

`JIRA_BASE_URL` (e.g. `https://acme.atlassian.net`) + the service account
email + API token (id.atlassian.com → Security → API tokens) in `.env`. Needs
browse on the in-scope project(s) only. Used for Block C JQL and account-ID
lookup (RUNBOOK step 6).

## Anthropic

The ask classifier runs company content, so it uses the **company-issued
Anthropic API key** (Commercial Terms, no training on inputs). Personal keys
are not acceptable here. `.env`: `ANTHROPIC_API_KEY`.

## Secret handling

Every secret lives in `.env` on the box (chmod 600, root-owned), loaded by
docker-compose. Nothing secret is ever committed; `.env.example` documents the
shape. Slack user tokens are the one runtime-acquired secret and live in the
`credentials` table of a database that is not exposed off the compose network.
If the box is compromised, rotate: the Entra client secret, the Slack app
(reinstall invalidates tokens), and the Jira token — the runbook lists the
three revocation points.

## Privacy boundaries (inherited, non-negotiable)

`config/filters.yaml` `do_not_ingest` enforces the hard privacy rules —
legal counsel correspondence, executive personal channels, board-only Jira —
**before** any candidate reaches the classifier. The service owner fills the
lists before week 1. Excluded content is dropped unlogged.
