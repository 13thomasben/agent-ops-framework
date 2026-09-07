# Slack posting identity — `@bot`

**Every Slack write produced by a skill in this repo goes out as `@bot`, not as the CEO.** The one exception is a broken dispatch path, which falls back to the connector *with a label saying so* — see *When the dispatch path fails*. An unlabeled CEO-authored post is never correct.

This is the canonical contract. Each skill's own `SKILL.md` carries the minimal recipe inline so it stays self-sufficient; this file is the reference for setup, edge cases, and troubleshooting.

---

## Why

The skills are automation. Before this change every report, DM, and thread echo was written through the Slack MCP connector, which is authenticated as the CEO's user account — so automation output was indistinguishable from the CEO typing, in channels where the difference matters (coaching, ticket flags, scorecards). Posting as `@bot` makes the automation legible: readers can tell a machine wrote it, replies go to a thread the automation owns, and the CEO's own messages stay theirs.

---

## The split: writes vs. reads

| Direction | Identity | How |
|---|---|---|
| **Writes** — channel posts, thread replies, DMs, scheduled messages, reactions on our own posts | `@bot` | Slack Web API over HTTPS with the `@bot` token (below) |
| **Reads — a thread or channel `@bot` is already in** (chiefly: replies to our own posts) | `@bot` | Slack Web API with the same token — `conversations.replies` / `conversations.history` |
| **Reads — everything else** — other people's channels, user profiles, user/channel search, permalinks of others' messages | the CEO's connector | Slack MCP connector tools (`slack_read_channel`, `slack_read_thread`, `slack_read_user_profile`, `slack_search_users`, `slack_search_channels`, …) |

**Corrected 2026-08-01.** This doc previously said the bot token was "scoped for posting" and told you not to widen it. That was wrong — the installed token already carries read scopes. Verified live:

```
chat:write, chat:write.customize, im:write, files:write,
channels:history, groups:history, im:history, im:read
```

That matters because **MCP connectors are not guaranteed to be present on a scheduled run.** Routines created through this account's meta-MCP tool store no connectors at all (the `connectors` parameter is disabled org-wide), so their sessions have no `slack_read_thread`. A skill that reads its own thread only through the connector will silently read nothing on those runs — which, for an approval loop, means approvals are never applied and nobody notices.

So: **read your own threads with the token.** It needs no connector, no extra grant, and it works wherever `slack.com` egress works.

```bash
# Replies to one of our own posts — the approval-loop read.
curl -sS -G https://slack.com/api/conversations.replies \
  --data-urlencode "channel=$CHANNEL_ID" \
  --data-urlencode "ts=$PARENT_TS" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
| jq -r '.messages[] | "\(.user // .bot_id)\t\(.ts)\t\(.text)"'
```

The parent message comes back as `messages[0]`; skip any message whose `user` is `U_EXAMPLE_BOT` (that is us). `ok:false` with `not_in_channel` means `@bot` was never invited — history scopes do not grant access to channels the bot isn't a member of, which is exactly why this is scoped to "threads we posted in".

The connector remains correct for everything else, because `@bot` is a member of only a handful of channels while the CEO's connector sees them all. Prefer the connector when it is available and the read is broad; use the token when the read is our own thread, or when the run may have no connector.

**Never reach for `slack_send_message`, `slack_send_message_draft`, or `slack_schedule_message` as the way you post.** Those write as the CEO. The dispatch path below is how a skill delivers; the connector's write tools survive only as the labeled last-resort fallback described under *When the dispatch path fails*, never as a first choice and never silently.

---

## Token

- **Env var:** `SLACK_BOT_TOKEN`.
- Supplied by the runtime: a GitHub Actions secret in the scheduled workflows, the environment's secret manager for cloud runs.
- **Never** echo it, log it, paste it into a Slack message, or commit it. Refer to it only as `$SLACK_BOT_TOKEN` in commands.
- If it is not set, the dispatch path is unavailable — see *When the dispatch path fails* below. The content still goes out, under a label saying why it isn't from `@bot`.

Required scopes on the `@bot` app: `chat:write` (posts), `chat:write.public` (post to public channels without an invite), `im:write` (DMs). `chat:write.customize` only if a skill needs to override the display name, which none currently do — the display name comes from the app's own config.

## Runner requirement: egress to `slack.com`

**The runner must be able to reach `slack.com` over HTTPS.** This is not a Slack permission — it's the network policy of the machine the skill runs on, and it is the first thing to check when bot posts stop working.

This bit everyone on the first live run (2026-07-29, bdr-call-coaching): the routine's sandbox denied `slack.com:443` at its egress proxy, so `chat.postMessage` never reached Slack and every report went out on the labeled fallback. **Inviting the bot to the channel does not help** — the request never left the container.

The confusing part is the asymmetry with the connector: **MCP connectors do not use the container's egress path** (the control plane brokers them), so `slack_read_channel` and friends keep working while a direct `curl` to the very same service is refused. Connector reads succeeding is *not* evidence that the dispatch path can post.

Diagnosing it, on the runner:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 12 https://slack.com/   # 000 + proxy 403 = blocked
curl -sS "$HTTPS_PROXY/__agentproxy/status" | jq '.recentRelayFailures'      # names the denied host
```

A `403` on `CONNECT` is an organization egress-policy denial. **Do not retry it or route around it** — the fix is to allow `slack.com` in the environment's network policy (Claude Code environment settings; see https://code.claude.com/docs/en/claude-code-on-the-web), not to change anything in a skill. `slack.com` alone is enough for everything in this doc — the Web API lives at `slack.com/api/*`. `hooks.slack.com` (incoming webhooks) and `files.slack.com` (uploads) are not used. GitHub Actions runners have open egress, so a skill running as a workflow is unaffected.

---

**The token in the environment is a bot token (`xoxb-…`), not a user OAuth token (`xoxp-…`).** That is the right credential here — a bot token is exactly what makes a post appear as the app instead of as a person — but it also means the author name on every post is the app's configured display name. If posts land under an unexpected name, fix it in the Slack app config (Basic Information → Display Information); don't paper over it per-call with a `username` override. Confirm what the token actually is with `auth.test` (recipe below) before debugging anything else.

---

## Recipes

All of these are plain `curl` against the Slack Web API. Build JSON payloads with `jq` rather than string-interpolating into a quoted heredoc — report bodies contain quotes, backticks, newlines, and `<@U…>` tags that break naive quoting.

`--rawfile` needs jq 1.6+. On a runner without `jq`, build the same payload with Python and pipe it in:

```bash
python3 -c 'import json,sys;print(json.dumps({"channel":sys.argv[1],"text":open(sys.argv[2]).read(),"unfurl_links":False,"unfurl_media":False}))' \
  "$CHANNEL_ID" /tmp/msg.txt | curl -sS -X POST https://slack.com/api/chat.postMessage \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json; charset=utf-8' --data @-
```

### Post to a channel

Write the message body to a file first (keeps newlines and quoting intact), then:

```bash
jq -n --arg ch "$CHANNEL_ID" --rawfile txt /tmp/msg.txt \
  '{channel:$ch, text:$txt, unfurl_links:false, unfurl_media:false}' \
| curl -sS -X POST https://slack.com/api/chat.postMessage \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json; charset=utf-8' \
    --data @- \
| jq '{ok, channel, ts, error}'
```

`ok: true` plus a `ts` means posted. Anything else — read *Failure modes*.

### Reply in a thread

Same call with `thread_ts` set to the parent message's `ts`:

```bash
jq -n --arg ch "$CHANNEL_ID" --arg ts "$PARENT_TS" --rawfile txt /tmp/reply.txt \
  '{channel:$ch, thread_ts:$ts, text:$txt, unfurl_links:false, unfurl_media:false}' \
| curl -sS -X POST https://slack.com/api/chat.postMessage \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json; charset=utf-8' --data @- | jq '{ok, ts, error}'
```

A thread reply on a message `@bot` posted needs no extra permission. Replying in a thread under *someone else's* message works too, as long as `@bot` can post in the channel.

### Permalink (for the trackers)

`chat.postMessage` returns `ts`, not a URL. Skills that log `slack_permalink` must resolve it:

```bash
curl -sS -G https://slack.com/api/chat.getPermalink \
  --data-urlencode "channel=$CHANNEL_ID" \
  --data-urlencode "message_ts=$TS" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" | jq -r '.permalink'
```

### DM a person

Open the IM conversation, then post to the returned channel id:

```bash
DM_CH=$(jq -n --arg u "$USER_ID" '{users:$u}' \
  | curl -sS -X POST https://slack.com/api/conversations.open \
      -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
      -H 'Content-Type: application/json; charset=utf-8' --data @- \
  | jq -r '.channel.id')
# then chat.postMessage with channel = $DM_CH
```

A bot DM lands in the `@bot` app's DM conversation with that person, not in their own saved-messages DM. That is the intent — the automation has its own channel to them.

### Schedule a message

Only when a skill explicitly schedules (the weekly scorecard's Monday runs). `post_at` is Unix epoch seconds, must be 5 minutes to 120 days out:

```bash
jq -n --arg ch "$CHANNEL_ID" --argjson at "$POST_AT" --rawfile txt /tmp/msg.txt \
  '{channel:$ch, post_at:$at, text:$txt, unfurl_links:false, unfurl_media:false}' \
| curl -sS -X POST https://slack.com/api/chat.scheduleMessage \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json; charset=utf-8' --data @- \
| jq '{ok, scheduled_message_id, post_at, error}'
```

Unlike a human-authored scheduled message, a bot one **can** be cancelled before it fires — `chat.deleteScheduledMessage` with the `scheduled_message_id`. Keep the id in the run summary.

### `@bot`'s own identity — pinned, don't resolve it

Skills that look for their own prior posts in channel history need the bot's user id. **Use these pinned values; do not spend a network call resolving them:**

| Field | Value |
|---|---|
| Display name (post author) | the app's configured display name — confirmed by the CEO 2026-08-11 |
| Bot user id (`<@…>`, message `user` field) | `U_EXAMPLE_BOT` |
| Bot id | `B_EXAMPLE` |
| Workspace | `ACME` (`T_EXAMPLE`) |

Pinning follows the same reasoning as the pinned channel IDs: a lookup is one more thing that can fail on a scheduled run, and this one fails *hard* where egress is blocked — `auth.test` is the first call to die, so a skill that resolves its own id at startup breaks before it can even reach its fallback.

## The display name **is** `@bot` — one app, two names

**Read this before "fixing" a doc that says `@bot`.** After `canvases:write` was added and the app reinstalled on 2026-08-02, `auth.test` began returning the app's configured name as `user`, so **posts in channel show the author under that display name**, which is not the literal string `bot`. The CEO confirmed on 2026-08-11 that the display name is correct — it is the app's name, and it is not going to be renamed to match the docs.

Every `@bot` in this repo means **that same app**: bot user `U_EXAMPLE_BOT`, bot id `B_EXAMPLE`. `@bot` is the internal name for the posting path — the token, the recipes, the fallback rule — and the display name is what a reader sees on the message. Nothing in these recipes breaks, and skills that find their own prior posts by message text still work, because the `user_id` never changed.

Two consequences:

- **Don't chase the mismatch.** A doc saying "posts as `@bot`" and a channel showing the display name are the same fact. Do not paper over it with a per-call `username` override, and do not rename the app to make the docs literally true.
- **Reader-facing text uses the display name.** Anything written for the people reading the output rather than maintaining the skill — the channel canvases in `docs/agent-canvases/` above all — names the bot as it appears in Slack. Internal skill docs keep `@bot`, because that is what the token and the failure modes are called.

Scopes as of 2026-08-02: `chat:write, chat:write.customize, im:write, files:write, channels:history, groups:history, im:history, im:read, canvases:read, canvases:write`.

Verified 2026-07-29 against the live token. If a reinstall ever changes them, re-verify from a machine with open network access and update this table:

```bash
curl -sS -X POST https://slack.com/api/auth.test \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" | jq '{ok, user, user_id, bot_id, team, error}'
```

---

## Formatting — this changed

The MCP connector accepted markdown-ish input and cleaned it up. The raw API does not: `text` is rendered as Slack **mrkdwn**, verbatim.

- **Bold is single-asterisk** `*bold*`. `**bold**` renders with the asterisks visible. Italic is `_italic_`.
- Links are `<https://url|label>` — **not** `[label](url)`.
- Tags are `<@USERID>`; channels `<#CHANNELID>`.
- Bullets: literal `•` or `-` at line start. No markdown tables — they render as raw pipes; use aligned text in a ``` code block when a skill needs a grid (the BDR rhythm grid already does).
- `unfurl_links:false` keeps report bodies from growing a preview card per link. Leave it off unless a skill wants the unfurl.

---

## Channel membership

`chat:write.public` covers public channels without an invite. Anything private, plus every channel where you want `@bot` visible in the member list, needs an explicit `/invite @bot`. Current delivery targets:

| Channel | ID | Skill |
|---|---|---|
| `#sales_prospect-meetings` | see the skill's `data/config.csv` | acme-call-intel |
| `#customer-success` | `C_EXAMPLE_CS` | customer-support-scorecard |
| `#customer-support-reporting` | `C_EXAMPLE_SUPPORT` | acme-ticket-daily-check |
| `#bdr-coaching` | `C_EXAMPLE_BDR` | bdr-call-coaching |
| `#market-intel-analysis` | `C_EXAMPLE_MARKET_INTEL` | hermes-market-intel same-day pings + Monday digest |
| `#inbound_leads` (**private** — invite required, **done**, verified 2026-08-21) | `C_EXAMPLE_LEADS` | acme-inbound-leads |
| `#applied-ai` (**private** — invite required) | `C_EXAMPLE_APPLIED_AI` | pre-call-primer delivery; the Step 0 suggestion batch from bdr-call-coaching, customer-support-scorecard, acme-ticket-daily-check, acme-call-intel, acme-inbound-leads and fleet-integrity-check; **every operational notice that used to be a DM** (below); slack-thread-hygiene's digest |
| `#applied-ai_demo` (**private** — invite required) | `C_EXAMPLE_DEMO` | demo, preview and validation runs only — never a skill's configured delivery target. `@bot` is a member. Also where the data vendor's Commitment Watchdog posts its daily digests, which `gtm-scorecard` reads as its commitments fallback |
| `#applied-ai_repo_health` (**private** — `@bot` already a member, verified 2026-08-21) | `C_EXAMPLE_REPO_HEALTH` | fleet-integrity-check's own report. Deliberately not `#applied-ai`: this skill reports *on* the delivery channels, and its audit of them does not belong in one of them |
| DM → any workspace member | resolved per run | slack-thread-hygiene nudges (`live` mode only) — **the one remaining DM surface**, see below |

## Operational notices go to `#applied-ai`, not to a DM

**Set by the CEO 2026-08-11: anything a skill sends as a DM goes to `#applied-ai` (`C_EXAMPLE_APPLIED_AI`) instead.** A DM is invisible to everyone but its recipient, so a notice that lands there can't be picked up by whoever is actually free to act on it, and it leaves no thread the next run can read. The channel gives every one of these a thread, which is the same interface the reports already use.

This covers, repo-wide:

- **Run-failure notes** from every skill — a blocked host, a dead token, a connector that wasn't attached, a meeting that couldn't be resolved.
- **`acme-call-intel`'s ambiguous-call notice** (Gate D) — a real external call it can't match to a deal with confidence.
- **`acme-ticket-daily-check`'s clean-run notice** — the one-liner that says the check ran and found nothing, so a silent run isn't mistaken for a quiet queue.
- **`slack-thread-hygiene`'s digest** — its `digest_channels` points at `#applied-ai`; `report_to` is empty.

Tag the person who owns the next move inside the message (`<@U_EXAMPLE_CEO>`, `<@U_EXAMPLE_OWNER>`) rather than relying on the DM to do the notifying.

### The one exception: thread-hygiene nudges

**`slack-thread-hygiene`'s nudges stay DMs, and this is not negotiable.** The entire purpose of that skill is that a threading correction arrives privately, from an automation rather than a colleague. Posting "you replied outside a thread" into a channel converts a housekeeping note into a public callout — the exact outcome the skill was built to avoid. Its *digest* (what went out, to whom) goes to `#applied-ai`; the nudges themselves do not.

---

## Failure modes

Read `.error` on every response. `ok: false` means nothing was posted — treat it as a failed step, not a warning.

| `error` | What it means | Do this |
|---|---|---|
| `not_in_channel` | private channel, or `chat:write.public` missing | `/invite @bot` to that channel; report the gap in the run summary |
| `channel_not_found` | wrong/stale channel id, or a private channel the bot can't see | re-resolve the id via the connector's `slack_search_channels`, then retry once |
| `invalid_auth`, `token_revoked`, `account_inactive` | token dead or rotated (a reinstall rotates it) | don't retry — go straight to the labeled fallback, and report the token as broken |
| `missing_scope` | app lacks `chat:write` / `im:write` | report the missing scope by name; a human fixes the app config |
| `ratelimited` | too many posts (~1/sec/channel) | honor `Retry-After`, retry once, then report |
| *no Slack response at all* — curl exit 7/28, HTTP `000`, or a proxy `403`/`407` on `CONNECT` | the runner can't reach `slack.com`; the request never got to Slack, so there is no Slack `error` field to read | don't retry, don't route around it — take the labeled fallback and report the blocked host. Fix is the environment's network policy, per *Runner requirement* above |
| `msg_too_long` | body over 40k chars | split: main message within the skill's format, remainder as a thread reply |

### Silent message splitting — the one that bites approval loops

`msg_too_long` (40k) is the *error*. Long before that, at roughly **4,000 characters**, Slack silently splits one `chat.postMessage` call into several messages — and returns only the **last** chunk's `ts`. Nothing fails; `ok:true` comes back and the post looks fine in the channel.

That quietly breaks any skill that saves the returned `ts` as a thread anchor: replies to the visible top of the report land on the FIRST chunk, whose ts you never saw. Observed live on 2026-07-31 (hermes-market-intel digest, ~5.5k chars): three approval replies sat unread for two days because the saved `ts` pointed at the tail.

Two defences, use both:

1. **Write side — stay under the limit.** Keep any message whose thread you intend to read under ~3,800 characters; push overflow into a thread reply on the anchor you just created.
2. **Read side — never trust one ts.** Sweep `conversations.history` for recent `@bot` posts with `reply_count > 0` and read each thread, rather than reading a single saved ts.

```bash
curl -sS -G https://slack.com/api/conversations.history \
  --data-urlencode "channel=$CHANNEL_ID" --data-urlencode "limit=25" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
| jq -r '.messages[] | select(.user=="U_EXAMPLE_BOT") | select((.reply_count//0)>0) | "\(.ts)\t\(.reply_count)"'
```
| `invalid_blocks`, `no_text` | payload built wrong | fix the payload — never work around it by switching identity |

### When the dispatch path fails

These skills run unattended. **A silent failure is worse than a post from the wrong identity** — no report at 4:15 PM reads as a quiet day, which is exactly the failure mode the whole automation exists to prevent. So the rule set by `bdr-call-coaching` (2026-07-29) is the repo-wide policy:

If the dispatch path cannot deliver for any reason — token missing from the environment, `ok: false`, curl/proxy error — after the one retry the failure table allows:

1. **Fall back to `slack_send_message`** for that message, to the same destination.
2. **Label it.** Append one italic line to the message body naming what happened, e.g. `_Posted under the CEO's account — the @bot post failed (invalid_auth)._` The content still lands, and nobody mistakes the identity for a choice.
3. Say exactly what failed in the run summary returned to whoever triggered the run: which skill, which channel, which Slack `error`.
4. Never silently skip, and never quietly post as the CEO without the label. Both hide a broken token for days.

If **both** paths fail, nothing was delivered: do not write state that claims otherwise (see each skill's logging rules — call-intel leaves the call out of `processed_calls.jsonl`, pre-call-primer skips the `log.csv` row and `last_run_at` bump) so the next run retries.

---

## Transition note (2026-07-29)

Posts before this date were authored by the CEO's account; posts after it are `@bot`. Two consequences for skills that read their own history:

- **Match on message text, not author.** `acme-ticket-daily-check` finds its prior posts by the `"Daily ticket check —"` prefix; that still works across the identity change. Do not add an author filter on the CEO, and do not assume every prior post is from `@bot` yet.
- **Threads span both.** Replies on pre-transition posts are still valid signal. Read them the same way; new echoes and replies go out as `@bot`.
