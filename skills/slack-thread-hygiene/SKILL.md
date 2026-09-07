---
name: slack-thread-hygiene
description: Scan Slack channels for messages that were clearly meant as thread replies but were posted as new top-level messages instead, then send the author a short nudge from the @bot app explaining how to reply in-thread. Use this for the scheduled daily thread hygiene sweep, and also when a user asks "check for threading mistakes", "is anyone breaking thread etiquette", "run the thread hygiene check", "who's replying outside threads", or names a channel and asks whether people are threading properly there. Trigger even if the user doesn't say "thread hygiene" but clearly wants Slack conversations audited for people replying in-channel instead of in-thread.
---

# Slack Thread Hygiene

Finds people who answered a message by posting again in the channel instead of replying in its thread, and nudges them privately. Optimized for precision: it is much better to miss five real cases than to wrongly correct one person.

**Reader-facing canvas:** `#applied-ai` (shared — its digest is one of three things that channel carries) carries a channel canvas describing this skill in plain language for the people who read its output — `docs/agent-canvases/applied-ai.md`. **Update it in the same change as any edit to the cadence, delivery surface, thresholds, or write authority here**, and drop a known-gap bullet from it when the gap closes. See *Changing an existing skill* in `PROCESS.md`.

Reads Slack through the connector (the CEO's account). Sends every nudge and digest as **`@bot`**. These are two different identities on purpose — the read happens as the connected user, the nudge arrives from the bot so nobody feels personally corrected by a colleague, and least of all by the CEO.

**Posting identity:** every Slack write from this skill — each nudge DM, the digest, any failure note — goes out as **`@bot`**, never as a person. Writes use the Slack Web API with the `@bot` token in `$SLACK_BOT_TOKEN`; reads (`slack_search_channels`, `slack_read_channel`, `slack_read_thread`, `slack_read_user_profile`) stay on the Slack MCP connector. Writes never go through `slack_send_message` / `slack_send_message_draft` except as the labeled fallback when dispatch fails. Full contract — recipes, error table, degradation rules: `contracts/slack-dispatch.md`.

**Schedule:** weekdays at 3:00 PM ET — mid-afternoon, when people are at their desks and a nudge about yesterday still connects to something they remember doing. Monday's run covers the weekend (see Step 3). Routine `ROUTINE_ID`, cron `0 19 * * 1-5`, entry prompt `prompts/slack-thread-hygiene.md`.

**The cron is UTC, so DST will shift it.** `0 19` is 3:00 PM EDT; when ET falls back to EST on 2026-11-01 the same expression fires at 2:00 PM ET. Move it to `0 20 * * 1-5` then, and back to `0 19` on 2027-03-14.

Bodies are Slack **mrkdwn**, rendered verbatim: `*bold*` single-asterisk (`**bold**` shows its asterisks), `_italic_`, `<@USERID>` tags, `<https://url|label>` links. Post with `unfurl_links:false` — a digest is mostly permalinks and would otherwise grow a preview card per line.

---

## Step 1: Load config and resolve mode

Read `config.yaml` from this skill's folder (`skills/slack-thread-hygiene/config.yaml`; copy `config.example.yaml` if it doesn't exist). Every value has a default, so the skill still runs if the file is missing or partial.

| Key | Default | What it does |
|---|---|---|
| `mode` | `report_only` | `report_only` posts one digest and nudges nobody. `live` DMs the actual authors. |
| `report_to` | `[]` | Slack user ID(s) that get a **DM copy** of the digest, in both modes. A single ID or a list. Empty is the norm — see below. |
| `digest_channels` | `[C_EXAMPLE_APPLIED_AI]` (`#applied-ai`) | Channel ID(s) the digest is posted to, in both modes. A single ID or a list. **This is the primary delivery path.** |
| `lookback_hours` | `24` | Fallback lookback when no previous digest can be found. |
| `monday_lookback_hours` | `72` | Fallback lookback on a Monday run, covering the weekend since the schedule is weekdays-only. |
| `max_lookback_hours` | `96` | Hard ceiling on the window, however long the real gap is. |
| `skip_channels` | `[]` | Channel names never scanned. |
| `max_items_per_dm` | `3` | Cap on examples listed in one nudge. |
| `min_confidence` | `high` | Only `high` fires. Set to `medium` to loosen. |
| `bot_token_env` | `SLACK_BOT_TOKEN` | Env var holding the `@bot` `xoxb-` token. |

**Never default to `live`.** If `mode` is unset, missing, or unparseable, run as `report_only`. `live` only ever comes from an explicit `mode: live` in the file — never from a prompt, a routine, or an inference that the run "looks clean." The CEO switched this skill to `live` on 2026-08-02 after reviewing a demo run.

**The digest goes to a channel, not to a DM** (set by the CEO 2026-08-11, and the repo-wide rule in `contracts/slack-dispatch.md`). `digest_channels` is `#applied-ai`; `report_to` is empty. A DM is invisible to everyone but its recipient and leaves no thread anyone can reply in, so every operational notice this skill produces — the digest, and the "couldn't sweep" notice in Step 2 — lands in the channel. `report_to` survives only as an opt-in DM copy for someone who specifically wants one.

**The nudges themselves stay DMs, and that is not a candidate for the same move.** The whole point of this skill is that a threading correction arrives privately, from an automation rather than a colleague. Posting one into a channel turns a housekeeping note into a public callout — the exact outcome it exists to avoid. **If `digest_channels` is empty and `report_to` is empty, the digest has nowhere to go: say so at the top of the run summary and do not send nudges**, because a `live` run whose record lands nowhere is unauditable.

`config.yaml` is committed, not gitignored: a scheduled run clones this repo fresh, so a config that only exists on someone's laptop means every routine run silently falls back to `report_only` defaults. It holds Slack user IDs and channel names — the same things already in this repo's other skills — and no secrets. `config.example.yaml` stays as the documented template.

**Check the token before scanning.** If the var named by `bot_token_env` is not set, say so at the top of the run summary and keep going — delivery will take the labeled fallback in Step 6. Never abort silently, and never substitute a human-authored post without the label.

## Step 2: Enumerate channels

Call `tool_search` for "slack" if the Slack tools aren't loaded yet.

Use `slack_search_channels` to list public channels. Then drop:

- anything in `skip_channels`
- archived channels
- channels the connector can't read
- channels with fewer than ~3 human members (threading is meaningless in a two-person channel)
- the skills' own delivery channels — `#bdr-coaching`, `#customer-support-reporting`, `#customer-success`, `#sales_prospect-meetings`, `#market-intel-analysis`, `#applied-ai`. These are automation feeds where `@bot` posts reports and humans reply in threads; a flat human message there is a reply *to a bot report*, not a threading mistake worth a DM.

Social and announcement channels are the main source of false positives. If `skip_channels` is empty, still use judgment and skip obvious ones like #random, #watercooler, #general, and anything that reads as a feed rather than a conversation. Note in the output which channels you skipped on judgment so the human can move them into config permanently.

If the workspace has a lot of public channels, don't try to read all of them in one pass. Work through them and stop when you've covered the active ones; a channel with no messages in the window costs one read and can be dropped immediately.

**This step needs the connector.** `@bot`'s own token can only read channels the bot is a member of (a handful), so a run with no Slack MCP connector cannot do this sweep. If the connector is unavailable, don't scan the few channels the bot can see and call it a run — post to every channel in `digest_channels` (and DM anyone in `report_to`) saying the run couldn't sweep, and stop.

This is the skill's live failure mode, not a hypothetical. Routines created through the meta-MCP `create_trigger` tool **store no connectors** — the parameter is disabled org-wide — so a routine created that way fires a session with no `slack_*` tools at all and every run stops here. Two ways out, either is fine:

- **Attach the Slack connector to the routine** from the claude.ai Routines UI (or create the routine there in the first place). Nothing in the skill changes.
- **Invite `@bot` to the channels being swept.** The token already carries `channels:history` and `groups:history` (see the shared doc), so a bot that is a member can read those channels directly and the skill runs connector-free. The cost is that `@bot` shows up in the member list of every conversation channel it watches, which is a visible presence in rooms where it otherwise only DMs. Prefer the connector; use this if routine connectors stay unavailable.

## Step 3: Read the window

**The window starts where the last run's window ended, read off the last digest.** Not off the calendar. The schedule is *supposed* to be a fixed 24h/72h cadence, but runs get skipped and fire times drift, and a window sized from the calendar silently drops every hour the schedule didn't actually cover. Derive it instead:

```bash
# A live run anchors only to the last *live* digest, looking straight past any
# report_only digests in between — a review run must not consume ground that
# nobody was ever nudged for. A report_only run anchors to the last digest of
# either mode, since it isn't taking anything away from anyone.
if [ "$MODE" = live ]; then MODE_RE=' · live'; else MODE_RE=''; fi

# Anchor source: first digest_channels entry. @bot posts there, so its own
# channels:history scope covers this read — no connector needed.
# history returns newest-first, so [0] is the last matching digest.
# Take the window END out of the footer rather than the post ts: the digest
# lands a few minutes after the read finished, and that gap would go unswept.
PREV_END=$(curl -sS -G https://slack.com/api/conversations.history \
  --data-urlencode "channel=$ANCHOR_CHANNEL" --data-urlencode "limit=100" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
| jq -r --arg m "$MODE_RE" \
   '[.messages[] | select(.user=="U_EXAMPLE_BOT")
     | .text
     | capture("Thread hygiene sweep · window \\S+ → (?<e>[0-9T:Z-]+)" + $m).e
    ][0] // empty')

# Transitional: digests posted before 2026-08-14 have no footer, so no recorded
# mode either — treat them as live (the config has been live since 2026-08-02,
# and assuming live keeps the window narrow rather than reaching back further).
#
# Gate this on "no footered digest of ANY mode", not "none matching my mode".
# Otherwise a live run that finds only report_only footers would fall in here
# and anchor to one of them by text match — exactly what the mode filter above
# exists to prevent. Footers present but no live one is a real answer, not a
# legacy channel: drop to the calendar fallback instead.
ANY_FOOTER=$(curl -sS -G https://slack.com/api/conversations.history \
  --data-urlencode "channel=$ANCHOR_CHANNEL" --data-urlencode "limit=100" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
| jq -r '[.messages[] | select(.user=="U_EXAMPLE_BOT")
          | select(.text|test("Thread hygiene sweep · window"))][0] // empty')

# Delete both this block and ANY_FOOTER once a footered digest exists in the
# anchor channel — from then on the capture above always wins.
if [ -z "$PREV_END" ] && [ -z "$ANY_FOOTER" ]; then
  PREV_END=$(curl -sS -G https://slack.com/api/conversations.history \
    --data-urlencode "channel=$ANCHOR_CHANNEL" --data-urlencode "limit=100" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  | jq -r '[.messages[] | select(.user=="U_EXAMPLE_BOT")
            | select(.text|test("thread hygiene|nudges? (sent|this run)";"i"))
            | .ts][0] // empty
           | if . == "" then "" else (tonumber|todate) end')
fi

# Still empty means no digest at all — use the calendar fallback (4) instead.
WINDOW_START=$(date -u -d "$PREV_END" +%s)
```

**Which digests count depends on the mode you're running.** A `live` run anchors only to the last **`live`** digest, reading straight past any `report_only` digests posted since — otherwise a review run would consume ground that nobody was ever nudged for. A `report_only` run anchors to the last digest of **either** mode; it takes nothing away from anyone, so there's no reason to make it re-cover a window that was already reported.

Resolve the anchor source in this order, and say in the digest which one you used whenever it isn't the first:

1. **First entry in `digest_channels`.** The canonical anchor.
2. **The DM to the first `report_to` user**, if `digest_channels` is empty — `conversations.open`, then `conversations.history` on the id it returns. The token carries `im:history`.
3. **A digest with no footer** (anything posted before this change): use its post `ts` as the window start, and treat it as `live` — the config has been `live` since 2026-08-02, and guessing `live` keeps the window narrow instead of reaching further back. Slightly conservative on the start too, since it re-covers the minutes between that run's read and its post, which is the right direction to err.
4. **No usable digest:** fall back to `lookback_hours`, or `monday_lookback_hours` on a Monday, and say in the digest that you fell back and why. This covers two cases — no digest in the channel at all, and (for a `live` run) footered digests that are all `report_only`. The second is not a legacy channel and must not drop to rule 3: footers are in use, so the absence of a `live` one is a real answer, and anchoring to a `report_only` digest by text match would quietly undo the mode filter.

Then clamp: **never scan further back than `max_lookback_hours`, whatever the arithmetic says.** If the routine has been dead for a week, the uncapped window is seven days across every channel — expensive to read, and a nudge about something eight days old is useless to the person receiving it. This skill's premise is that a nudge about yesterday still connects to something the reader remembers doing. When the gap exceeds the cap, scan the capped window and state plainly in the digest how many hours went unread, so a human can decide whether that matters.

Read each surviving channel over `WINDOW_START` → now with `slack_read_channel`.

**The invariant this buys you: consecutive `live` windows tile exactly — no gap, no overlap.** So no hour goes unswept when a run is skipped or fires late, and nobody is ever nudged twice for the same message. There is still no state file; the digest *is* the state, which is why the footer in Step 6 is not optional and why its mode field is load-bearing rather than decorative.

A `report_only` window may overlap `live` ground, and that is correct — reporting a message doesn't nudge anyone for it, so a later `live` run should still get the chance to. The reverse never happens: `live` never re-covers `live`.

One consequence to know about. A long `report_only` stretch means the next `live` run reaches back across all of it, so its window can be far wider than a day. `max_lookback_hours` clamps that, and the clamp gets reported — but if you've been running `report_only` for a week and then switch to `live`, expect the first live run to be reporting a truncated window rather than quietly covering everything since.

Ad-hoc runs are no longer the hazard they were. They used to re-cover ground the next scheduled run would read again; now an ad-hoc `report_only` run consumes only new reporting ground and leaves the nudge anchor exactly where it was.

## Step 4: Find candidate pairs

A candidate is a pair of messages: an earlier message A, and a later top-level message B that looks like it was answering A.

Mechanically, B is top-level when it has no `thread_ts`, or when `thread_ts` equals its own `ts`. That part is unambiguous. The judgment is whether it should have been a reply.

Flag a pair only when most of these hold:

- B was posted within about 30 minutes of A
- A and B are from different people
- A has zero thread replies, or very few
- B is responsive rather than generative: it answers a question A asked, @-mentions A's author, agrees or disagrees with A, or continues A's specific point
- B doesn't stand on its own — read in isolation, it would confuse someone

Strong tells: B starts with "yes", "no", "agreed", "done", "thanks", "good call", "+1", or names A's author directly. B is short and refers to something with a pronoun ("that works", "I'll handle it") whose antecedent is only in A.

Do **not** flag when:

- B introduces a new topic, even if it lands soon after A
- A and B are part of a fast back-and-forth between two people. Rapid flat exchange is normal Slack and correcting it is obnoxious.
- Either message is from a bot or an integration. That includes `@bot` itself (`U_EXAMPLE_BOT`) — every skill in this repo posts through it, so its reports would otherwise read as a wall of un-threaded top-level messages. Never nudge a bot, and never count a bot post as the A of a pair.
- B is a broadcast of a thread reply (Slack's "also send to channel"), which has a `thread_ts` and is not a mistake
- A is itself an announcement with no question in it
- More than about an hour separates them
- The channel's established norm is flat conversation. Read the surrounding day before deciding.
- You're reconstructing intent from thin evidence. If you have to argue for it, it isn't high confidence.

Assign each candidate `high` or `medium`. `high` means someone reading the two messages side by side would immediately say "yeah, that should have been a thread reply." Anything requiring explanation is `medium` at best.

Pull permalinks for both messages so the nudge can link to them. Take them from the connector read where it returns them; otherwise build them as `https://<workspace>.slack.com/archives/<channel_id>/p<ts with the dot removed>` (e.g. `ts` `1754150400.123456` → `p1754150400123456`). `chat.getPermalink` with the bot token only resolves channels `@bot` is a member of, so it is not the path for other people's channels.

## Step 5: Group and cap

Group candidates by author, not by channel. Then:

- Drop anything below `min_confidence`
- One DM per person per run, regardless of how many times they did it
- List at most `max_items_per_dm` examples, newest first, and say how many more there were if you truncated
- Skip anyone with exactly one `medium` hit; a single soft case isn't worth a message

If a single person accounts for a very large share of the day's hits, don't escalate the tone. Flag it in the digest for a human to handle as a conversation instead.

## Step 6: Deliver

Every message below is a `@bot` DM: `conversations.open` on the user ID, then `chat.postMessage` to the channel ID it returns, both with the token from Step 1. Write the body to a file first — it has newlines, `<@…>` tags, and `<url|label>` links that naive shell quoting mangles.

```bash
DM_CH=$(jq -n --arg u "$USER_ID" '{users:$u}' \
  | curl -sS -X POST https://slack.com/api/conversations.open \
      -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
      -H 'Content-Type: application/json; charset=utf-8' --data @- \
  | jq -r '.channel.id')

jq -n --arg ch "$DM_CH" --rawfile txt /tmp/nudge.txt \
  '{channel:$ch, text:$txt, unfurl_links:false, unfurl_media:false}' \
| curl -sS -X POST https://slack.com/api/chat.postMessage \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json; charset=utf-8' --data @- \
| jq '{ok, channel, ts, error}'
```

Slack returns HTTP 200 with `ok: false` on failure, so check the `ok` field rather than the status code, on **both** calls. On `ok: false`, follow the shared doc's failure table: retry once where it says to, then fall back to `slack_send_message` with an italic line naming the failure (`_Sent from the CEO's account — the @bot DM failed (invalid_auth)._`) and report it in the run summary. Never an unlabeled human DM, never a silent skip — a nudge that arrives from a colleague instead of the bot is exactly the outcome this skill is built to avoid, so if the label can't go with it, don't send that nudge at all and say so in the digest instead.

Keep any single message under ~3,800 characters. Slack silently splits longer posts into several messages and returns only the last chunk's `ts`. For a long digest, send the summary first and push the overflow into a thread reply on the `ts` it returns.

The digest is delivered the same way regardless of mode: **posted to every channel in `digest_channels`** (`chat.postMessage` straight to the channel ID, no `conversations.open`), plus a DM copy to anyone in `report_to` if that list is non-empty (`conversations.open` then `chat.postMessage`). Do both, independently — a failure on one delivery path doesn't cancel the other, and each gets its own line in the failure table if it fails. A private channel in `digest_channels` that `@bot` hasn't been invited to fails with `not_in_channel`; report that by name rather than retrying or routing around it.

`#applied-ai` is both the digest destination **and** a channel this skill never scans (Step 2). That is not a contradiction — it's what stops the skill reading its own digests back as un-threaded top-level messages.

**Content differs by mode** — `report_only` is a review artifact and stays detailed (below); `live`'s digest is deliberately short (see the `live` section) because the nudges already carry the detail and a human reading the digest just needs to know what went out.

### The footer — required on every digest, both modes

End every digest with this line, exactly this shape:

```
_Thread hygiene sweep · window 2026-08-13T15:04:23Z → 2026-08-14T18:59:58Z · live_
```

Both timestamps are ISO 8601 UTC. The end is the moment the channel reads finished, not the moment you post. The last field is the mode this run actually ran in — `live` or `report_only`, matching what Step 1 resolved.

**This line is how the next run knows where to start** (Step 3) — it is the skill's entire state. A digest without it forces the next run onto the weaker post-`ts` fallback, and a digest with a wrong window silently makes the next run skip or re-cover ground. Never omit it, never reformat it, and never round the timestamps.

**The mode field is load-bearing, not a label.** `live` runs anchor only to `live` digests, so writing the wrong mode does real damage in both directions: stamp `live` on a `report_only` run and the next live run starts after a window nobody was nudged for, dropping those mistakes for good; stamp `report_only` on a live run and the next live run reaches back across ground it already nudged, risking a second nudge for the same message. Write what actually happened. If the digest is long enough to need splitting, the footer goes on the **first** message, not the overflow thread reply, since that is the message the history sweep finds.

Bracket the window with the same clock you scanned with: capture the end timestamp when the last channel read returns, before you start composing.

### report_only

Post the digest to every channel in `digest_channels`, plus a DM copy to anyone in `report_to`. Include every candidate with its confidence, both permalinks, and the reasoning in one line. This is a review artifact, so show the `medium` ones too, marked clearly. Also list channels skipped on judgment and any that failed to read.

Lead with the count and the shape of it: "14 candidates across 6 channels, 9 high / 5 medium." Then the detail.

### live

For each person, DM the nudge. The opening line is fixed — send it verbatim:

> I've been checking to make sure channel hygiene is up and kept so your teams can work as efficiently as possible. One message yesterday looked like it was meant as a reply to an existing thread:
>
> • <https://…|your message in #channel> → <https://…|the thread it belonged to>
>
> Replying in-thread keeps channels readable and makes sure the right people get notified. Hover a message and pick *Reply in thread*. More here: <https://slack.com/help/articles/115000769927-Use-threads-to-organize-discussions|Slack's guide to threads>
>
> No action needed on this one, just for next time.

Two things flex, nothing else:

- **Count and timeframe.** "One message yesterday looked like it was" / "A couple of messages yesterday looked like they were" / "A few messages last week looked like they were" — match the actual number and the actual window (a Monday run covers the weekend, not "yesterday"). Close on "No action needed on this one" or "on these" to match.
- **The bullets.** One line per example, newest first, capped at `max_items_per_dm`. Each is `<permalink|your message in #channel> → <permalink|the thread it belonged to>`. If examples were truncated, add a line saying how many more there were.

Do not introduce the sender, name the skill, or call it a bot — the message comes from the bot app and the avatar already says so. No greeting line, no sign-off beyond the closing sentence.

Keep it light. This is a housekeeping note, not a performance issue. Never use language implying someone was reported, tracked, or is in trouble, and never mention who else got a nudge.

The DM lands in the `@bot` app's conversation with that person, which is the intent: it reads as automation, and any reply goes to the bot rather than to a person. Slack files bot DMs under "Apps" in the sidebar, not the regular Direct Messages list — worth knowing before concluding a DM never arrived.

After a `live` run, post a short record to every channel in `digest_channels` (plus a DM copy to anyone in `report_to`) — not the `report_only` review artifact. State only: how many nudges went out and to whom (or that none went out), one line each on why, and any delivery failures. No candidate reasoning, no channel coverage, no skip list — that detail lives in the nudges themselves and in the run summary returned to whoever triggered the run.

```
1 nudge sent: <name> (#channel — <one-line reason>).
No delivery failures.

_Thread hygiene sweep · window 2026-08-13T15:04:23Z → 2026-08-14T18:59:58Z · live_
```

or, when nothing fired:

```
No nudges this run.

_Thread hygiene sweep · window 2026-08-13T15:04:23Z → 2026-08-14T18:59:58Z · live_
```

Add a line above the footer whenever the window wasn't the ordinary one — the anchor came from somewhere other than the first `digest_channels` entry, the gap was clamped by `max_lookback_hours`, or you fell back to the calendar. One sentence, e.g. `Window widened to 27h — no run on Wed Aug 12.`

## Guidelines

- Precision over recall, always. One wrong nudge costs more trust than ten missed cases earn.
- Never nudge someone for a message in a channel where you skipped the surrounding context. If you couldn't read the full window, don't judge it.
- If a run finds nothing, say so plainly rather than lowering the bar to produce output.
- Don't quote people's messages at length in the digest or the nudge. Link to them.
- If the connector can't read a channel, or the bot token is missing, or a DM failed to send — fail loudly in the digest and the run summary. Silent partial runs are how this rots without anyone noticing.
