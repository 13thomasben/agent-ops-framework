# Agent description canvases

Plain-language guides to what each automation in this repo does, written for the people who read its output — not for the people who maintain it.

One per Slack channel that a skill in this repo delivers into, on the pattern of the **Market Intel Agent Description** canvas on `#market-intel-analysis`. Three sections and nothing else: what the automation is, how it works, and how to interact with it. Short enough that someone actually reads it.

These files are the source of truth. The Slack canvases are rendered from them, so **edit here and re-publish** rather than editing a canvas in place.

## Coverage

`channels.json` is the machine-readable version of this table, and what the drift check and the publish step read. Keep the two in step.

Six of the seven are published; `#inbound_leads` is waiting on the bot being invited to that private channel. **To change one, edit its source file and call `canvases.edit` with its `canvas_id`** — a second `conversations.canvases.create` makes a second canvas rather than updating the tab.

| Channel | Canvas source | Title | Canvas ID |
|---|---|---|---|
| `#market-intel-analysis` | *(no source file here yet)* | Market Intel Agent Description | `F_EXAMPLE_1` |
| `#bdr-coaching` | `bdr-coaching.md` | BDR Coaching Agent Description | `F_EXAMPLE_2` |
| `#customer-success` | `customer-success.md` | CS Scorecard Agents Description | `F_EXAMPLE_3` |
| `#customer-support-reporting` | `customer-support-reporting.md` | Daily Ticket Check Agent Description | `F_EXAMPLE_4` |
| `#inbound_leads` (private) | `inbound-leads.md` | Inbound Leads Agent Description | *(not published yet — bot not in channel)* |
| `#sales_prospect-meetings` | `sales-prospect-meetings.md` | Call Intel Agent Description | `F_EXAMPLE_5` |
| `#applied-ai` (private) | `applied-ai.md` | Applied AI Channel Agent Description | `F_EXAMPLE_6` |

Channel IDs and the skills each canvas covers are in `channels.json`.

**Not covered, and why:**

- **`linkedin-watch` and `webagent`** are building blocks with no Slack delivery of their own. `linkedin-watch` is described inside the market-intel canvas, which is the skill that calls it — so a change to it belongs there.
- **Thread-hygiene nudges.** The one remaining DM surface in the repo, and deliberately so: the whole point is that a threading correction arrives privately from an automation rather than from a colleague. Its *digest* is covered on `#applied-ai`, and the nudges are described there too.

## Conventions

**Three sections, in this order, every time.** Set by the CEO 2026-08-11:

1. **Agent description** — what it is, in a couple of sentences.
2. **How it works** — cadence as a tempo, and what it actually does.
3. **How to interact with it** — the reply table. This is the section readers come back for.

Then **Who to ask**, which is just the Owner.

**No "honest limits" or "known gaps" sections.** The first pass had both. They were long, they aged badly, and they buried the part people needed. Keep a limit only where it changes how someone reads the output — that Fireflies names are unreliable, that a capture flag means the transcript wasn't the meeting — and put it inline where it's relevant rather than in a list at the end.

**Keep them short.** Roughly 50 lines. The first pass ran 140–190 and nobody was going to read it. If a rule needs three sentences of justification, the justification belongs in the `SKILL.md`, not the canvas.

**Tag only the Owner** (`U_EXAMPLE_OWNER`) and **the bot** (`U_EXAMPLE_BOT`). No other team member gets tagged anywhere in a canvas — a canvas is a reference document, and a tag in one is a notification nobody asked for. Naming someone in an *example* ("moved to a teammate") is fine; tagging them is not.

**The bot's display name in Slack may differ from `@bot`**, which is the internal name for the same app — see `contracts/slack-dispatch.md`. Writing the mention as `![](@U_EXAMPLE_BOT)` sidesteps the question, since Slack renders the current display name.

**Tempo, not timestamps.** Say "once a day, every weekday morning" — not "weekdays 8:00 AM ET". A canvas that names a clock time goes stale the first time a routine moves, and a reader almost never needs the minute; they need to know whether to expect this daily or monthly. Windows and lookbacks *are* worth stating ("covering the prior Monday–Sunday"), because those change what the numbers mean.

**No multi-line blockquotes.** A canvas joins consecutive `>` lines into one paragraph, so a multi-line quote silently collapses — on the first publish, the BDR canvas's proposal example ran together into `*Proposed HubSpot change* — @Rep Company · Example Landscaping LLC Lifecycle stage: …`, which reads as a company named "Rep Company". Use a fenced code block for any verbatim message example. Single-line blockquotes are fine. Slack mrkdwn isn't rendered inside a fence, so write `@Rep` rather than `<@U…>`.

**The title is set on create and cannot be changed.** `canvases.edit` rejects a `title` argument, so a retitle means delete and recreate. The first five went out untitled for exactly this reason — always pass `title`.

## Format

Canvas-flavoured markdown, per Slack's rules — which are *not* the same as GitHub markdown:

- Headings `#`, `##`, `###` only. Never `####` or deeper, and never a heading inside a list item.
- User mentions are `![](@USERID)`, channel references `![](#CHANNELID)`. Always the ID, never the name. A mention on its own line renders as a profile card; inline it renders as a mention.
- Links are `[label](url)` — not `<url|label>` (that's Slack *message* mrkdwn, a different format).
- No code blocks inside list items. Blockquotes and code fences need a blank line either side of a list.
- Bulleted lists nest only inside bulleted lists; numbered only inside numbered.

## Publishing

Canvases are created with the bot's token (`$SLACK_BOT_TOKEN`), which carries `canvases:read` and `canvases:write` as of 2026-08-02. That is how the market-intel canvas was authored, and it is why every canvas shows the bot as its author.

A **channel canvas** — the tab next to Messages, which is what these should be — is created against the channel:

```bash
jq -n --arg ch "$CHANNEL_ID" --arg t "BDR Coaching Agent Description" --rawfile md ./bdr-coaching.md \
  '{channel_id:$ch, title:$t, document_content:{type:"markdown", markdown:$md}}' \
| curl -sS -X POST https://slack.com/api/conversations.canvases.create \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json; charset=utf-8' --data @- \
| jq '{ok, canvas_id, error}'
```

**Always pass `title`.** Without it the canvas is created as "Untitled" and there is no way to fix it in place — `canvases.edit` rejects a `title` argument, so a retitle is delete + recreate. The first round went out untitled and had to be republished.

Updating the *content* is `canvases.edit` with the stored `canvas_id` and a `document_content` replace operation. Record each `canvas_id` in `channels.json` — that is what makes a change an update rather than a second canvas on the same channel. A channel will happily hold several.

Two things to check before publishing:

1. **The bot must be a member of any private channel** — `#applied-ai`, `#inbound_leads`. Otherwise the call fails `not_in_channel`, and no canvas scope substitutes for membership.
2. **The runner needs egress to `slack.com`.** Same requirement as every other Slack write in this repo; see `contracts/slack-dispatch.md`.

## Keeping them true

**A skill and its canvas ship together.** A canvas that has drifted is worse than no canvas, because people act on it. The full rule is *Changing an existing skill* in `PROCESS.md`; the short version:

- **Four things readers rely on:** cadence, delivery surface, thresholds and rules, and write authority. A change to any of them updates the canvas in the same change.
- **A limit that gets fixed comes out of the canvas in the same change that fixes it.** Canvases no longer carry a limits section, but the few limits that survive inline — Fireflies name accuracy, what a capture flag means — describe things somebody is presumably working on. A stale one makes readers distrust the parts that are still true.
- **A change to a shared contract** (`contracts/*.md`) touches every canvas — those rails are described in all of them.
- Each canvas ends by telling readers that a mismatch between the canvas and what they're seeing is a bug worth flagging. That only works if it's true.

`.github/workflows/canvas-drift.yml` leaves a non-blocking annotation on any PR that changes a `SKILL.md` without touching its canvas, naming the file to look at. It's a reminder, not a gate — "nothing a reader relies on moved" is a legitimate answer to it.

Resist the urge to grow them back. Every addition is a sentence someone has to read before finding the reply table, which is the part that actually gets used. If something needs explaining at length, it belongs in the `SKILL.md`.
