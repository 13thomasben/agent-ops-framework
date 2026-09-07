# Slack output format — the house standard

**Canonical for the Slack *message* surface.** Every channel post, thread reply, DM, and scheduled message a skill in this repo produces is bound by this file. Its companion contracts: `slack-dispatch.md` governs **how** a skill posts (identity, token, failure modes), `thread-feedback.md` governs **what it does about replies**, `write-surfaces.md` governs **whether it may write at all**. This file governs **what the reader sees**.

Where a skill's own `SKILL.md` and this file disagree, this file wins — except where the skill's rule is *tighter*, which always survives.

**Two surfaces are out of scope, and both invert these rules.**

- **Canvases.** Different format entirely: `[label](url)` not `<url|label>`, `![](@U…)` not `<@U…>`, real markdown tables, `**bold**`. They follow `docs/agent-canvases/README.md`. Do not apply this file to a canvas, and do not apply that file here.
- **Anything a human pastes into Slack's composer** rather than sending through the API — today that is `tracker-weekly-brief`, which builds a rich-text page for the Owner to paste. The composer renders *standard* markdown, so `**bold**` is correct there and single-asterisk mrkdwn does not format at all. Everything in §2's banned table and §10's first two checks is inverted on that path. The same applies to the labeled MCP-connector fallback in `slack-dispatch.md`: the connector takes standard markdown, so a fallback message converts `*bold*` to `**bold**` and `<url|label>` to `[label](url)` on the way out.

---

## Why this exists

Sixteen skills post to Slack through the API. Each one independently invented its own answer to the same four questions — where the lede goes, what gets bold, how a label attaches to a value, how long is too long — and the answers diverged. The result is a family of outputs that are individually defensible and collectively unreadable: bullet characters differ (`•` vs `-`), separators differ (`·` vs `/` vs commas), stated length ceilings differ by a factor of six (600 vs 3,800 chars), and the lede lands anywhere from line 3 to line 7.

Reading is the whole point. A number nobody can find is worth the same as a number nobody computed.

### The four defects this file fixes

**1. Provenance before content.** Most reporting skills open with a title, then one or two lines of when-it-ran and what-it-covers, then a section header carrying a parenthetical legend. The first actual fact lands on line 5 to 7. The reader pays a toll before receiving anything.

**2. Emphasis with no budget.** Two opposite failures, same effect. *Saturation*: a full market-intel digest carries 25+ bold spans — title, every section header, every company name, every command — so bold distinguishes nothing. *Uniformity*: the sprint readout bolds ten section headers in thirty-nine lines, so the page reads as evenly-weighted stripes and nothing marks importance. Bold that marks structure cannot also mark significance.

**3. Horizontal packing.** The honesty rules are right and they have a cost: every figure carries its denominator, its window, and its caveat, and all of that is currently pushed *into the line*. A single bullet routinely holds four to six fields joined by three or four different separator types. Nothing is vertically alignable, so the eye cannot build a scan path down a list — every line must be read left to right in full.

**4. No verdict, no ordering.** Sections appear in fixed order at equal weight. Nothing tells the reader which figure moved, which is bad, or where to look first. In the sprint readout the drift block — literally *what changed since last week* — is second to last and optional.

### Two defects that are live bugs, not style

- **`**bold**` is shipping.** Observed in a Monday card on 2026-08-20: `**You don't carry a deal book**` posted with the asterisks visible. The `text` field renders mrkdwn, where bold is a single asterisk. Double-asterisk bold has been documented as broken in four places in this repo and is still reaching readers.
- **Instruction text is inside posted templates.** `company-scorecard`'s skeleton contains `*Worth reconciling* (only when computed and self-reported diverge; omit otherwise)` and three bullets ending in `· ...`; `customer-support-scorecard`'s contains the bullet `- Skip this section entirely if there's nothing material`. These are notes to the author sitting in the block a literal renderer will post.

---

## 1. Message anatomy — five slots, this order, every time

```
1  TITLE        one line, stable matchable prefix
2  LEDE         one sentence: the answer
3  BODY         the evidence, ordered by what needs acting on
4  ASK          who does what next          (omit when there is none)
5  PROVENANCE   one line, last              (omit only for a glance post)
```

**The lede is slot 2 and nothing displaces it.** One sentence, plain, no formatting other than bold on the single figure that carries it. It answers the question the post exists to answer: what moved, what is off, what needs a human. It is not a restatement of the title, not a count of what the post contains, and never the window or the run time.

Good ledes:

```
Two of three goals are ahead. Pipeline added is already past the month target.
Two checks moved more than 5pp this week. The other four held.
4 tickets need attention.
Nothing moved against you this week.
```

Bad ledes — all of these are real:

```
_Computed 06:02 ET · posts due 10:00 AM PT · numbers carry their denominators_
*Goals* (one line each, computed · self-reported · Δ vs prior week)
_This is not velocity._ It is the board's current contents, which changed during the sprint…
I've been checking to make sure channel hygiene is up and kept so your teams can work as efficiently as possible.
```

**Provenance goes last, in one line.** Run time, window, source, mode, read-only status, correction instructions — all of it, collapsed into a single italic line (mrkdwn) or a single `context` block (Block Kit). If a caveat changes how one specific number reads, it belongs *inline with that number*, not in a preamble that applies to everything.

**Where a skill's own steps mandate a provenance line in slot 2, this file wins and that line moves to the bottom.** `sprint-integrity-preplanning` currently requires both a second line naming the run time *and* an opening line naming what planning can act on; the actionable line is the lede and the run time goes last.

**A standing caveat that has not changed in a month is not information.** Weekly-identical boilerplate stops being read and dilutes the lines that did change. Move it to the channel canvas and reference it, or cut it. In the sprint readout this is roughly a quarter of the character budget.

**The title line stays byte-stable.** Thread discovery matches on first-line prefixes (`*Daily ticket check —`, `*Pipeline brief · `, `*Week in review · `). Changing a title is changing a matcher — see `thread-feedback.md`. Reserved markers keep their exact form, em dashes included.

**Moving a title into a `header` block is a matcher change.** A `header` block takes `plain_text`, which does not render mrkdwn — so `*Daily ticket check — Wed, Aug 19*` becomes `Daily ticket check — Wed, Aug 19`, with no asterisks. Every Step 0 matcher keyed on the asterisk form stops matching, the skill stops finding its own threads, and the failure is silent: it looks like a week with no replies. When a skill moves to blocks, the byte-stable prefix must also be carried in the `text` fallback and the matcher must read `text`. See §9.

---

## 2. Emphasis budget

**Bold: one span per section, plus one for the whole message.**

Bold does exactly one job in a given message: it marks the thing the reader is looking for. If bold marks section structure, it cannot also mark significance — so pick.

- **Block Kit available** → structure is carried by `header`, `context`, and `divider` blocks. Every bold span left in the body is then free to mark a value. This is the better arrangement, and the main reason to use blocks.
- **Plain mrkdwn** → a section header may be bold, and then the section gets *one* additional bold span, on the figure that changed. A section with nothing notable in it gets none.

**Bold the number, not the sentence.** `*$175,995* across 13 deals` — not `*$175,995 MTD across 13 deals — that is your full month target already met*`. A bolded clause is a bolded paragraph with extra steps.

**Italic is for provenance, asides, and the fallback label. Never for emphasis.** Two italic spans per message is the ceiling.

**`code` spans are for identifiers and fixed-width tokens** — a Jira key's priority, a field name, a status value. They are also the cheapest way to get a fixed-width column into a plain-mrkdwn bullet list: `` `S2 ` `` and `` `Med` `` line up where `[Bug, S2]` and `[Support, Med]` do not.

**Banned outright** — on the API path. All three are *correct* on the paste and connector-fallback paths named at the top of this file.

| Never | Why | Instead |
|---|---|---|
| `**bold**` | renders the asterisks visibly | `*bold*` |
| `[label](url)` | renders literally | `<url\|label>` |
| `<@USERID\|Name>` | pipe-label is a *link* feature; renders as bracket text | `<@USERID>` |
| `@here` / `@channel` | no automation earns a workspace ping | tag the one owner |
| bold on a full clause or sentence | destroys the budget | bold the value |
| italic for emphasis | collides with provenance | bold, or restructure |

### Emoji: default to none

Set by the CEO on 2026-08-21, and it reverses both this file's first draft and `acme-inbound-leads`'s own stated rule that emoji were load-bearing: *"let's also get rid of the emojis. I think just using bolds and bullet point formatting is good enough. The emojis are a lot."*

That change (PR #109) is worth reading before writing any template, because it arrived at §2 and §3 of this file from the reading end rather than the writing end. Three things had to be untangled and each one generalises:

- **The `🟢 🟡 🔴` fit read was a colour, not a word.** It became a `*Fit:*` line carrying one of three words. A colour cannot be quoted in a reply, searched for, or read aloud in a meeting.
- **The emoji *were* the labels.** A bare building-emoji line had no name at all, so every field gained an explicit bold label. This is the one-idea-per-line rule: a field with no label is a value the reader has to identify from context.
- **The header emoji was a thread-discovery matcher.** Three generations of it sat in the channel's history, so Step 0 now matches the bolded text core and ignores surrounding decoration. Changing decoration silently changed a matcher — the §1 title warning, in the wild.

So: bold labels and bullets carry the scanning job. A glyph may still encode one binary state where the alternative is a word repeating on every line — `webagent`'s `:white_check_mark:` / `:x:` on run status is the surviving case — and a severity marker may keep one glyph where it marks the exception rather than the rule. Everything else: cut it and put a bold label where it was. Never two glyphs for one state, and never a glyph a reader cannot name.

---

## 3. One idea per line

**A line carries at most two label:value pairs, and only when they share a denominator.** Three or more is a table.

This is the rule that replaces horizontal packing. Today:

```
Carried from an earlier sprint: 20/76 (26.3%) · in 3+ sprints: 14/76 (18.4%)
Plays per call: X.XX (n=..) · slot-locked X% · dated next X% · 4-wk trend [↑↓→]
Opened {N} / resolved {N} / net {+N} (ratio {R})
• *PROJ-123* [Bug, Med] Customer A — repro contradiction unresolved 27h. <@U…>: align on whether…
```

Each of these makes the reader parse a different grammar. The first mixes a fully-spelled label with an abbreviated one. The second puts four metric names and four values on one wrapped line. The third gives four numbers of which three are derivable, and needs a sign convention stated nowhere in the post. The fourth runs six fields through four delimiter types, with the owner — the single most-scanned field — in position five, mid-sentence.

**Every field carries a label a reader can say out loud.** No bare glyphs, no positional-only fields. This is what PR #109 established on `#inbound_leads`.

**Where the same field appears on every line, put it in the same position on every line, and put the most-scanned field first.** A list grouped by owner is read once per person; a list where the owner floats mid-sentence is read in full by everyone.

---

## 4. Tables — the rule that changed

> **Superseded:** `slack-dispatch.md` previously said *"No markdown tables — they render as raw pipes; use aligned text in a ``` code block."* That is still true of the **`text` field**, and false of the message as a whole. Slack has native `table` and `markdown` blocks, both reachable from the existing dispatch path by passing `blocks` alongside `text`.
>
> **Verified end to end.** Probes 1–6 posted to `#applied-ai_demo` on 2026-08-20: `chat.postMessage` accepted `header`, `context`, `divider`, `section`, `table`, and `rich_text` (with `indent` and `rich_text_quote`). `rich_text` nesting renders as `◦` sub-bullets. The `table` block renders a real grid with right-aligned numeric columns — confirmed visually by the Owner on 2026-08-25, which took a human because the read API does not return table cells (see §9).

| Shape of the data | Use |
|---|---|
| ≥3 rows × ≥3 columns of like-shaped values | native `table` block |
| 2 columns of label → value | `section` two-line pattern, or `rich_text` with an indented second level |
| a grid the reader will copy out | aligned text in a ``` fence |
| anything, and `blocks` is unavailable on this path | ``` fence, per the old rule |

**`table` block, the parts that matter.** First row is implicitly the header. `column_settings` sets `align` (`left`/`center`/`right`) and `is_wrapped` per column. Limits: 100 rows, 20 cells per row, 10,000 characters per message aggregate. Cells are `raw_text`, `raw_number`, or `rich_text` (which accepts bold, links, mentions).

```json
{
  "type": "table",
  "column_settings": [{"is_wrapped": true}, {"align": "right"}, {"align": "right"}],
  "rows": [
    [{"type": "raw_text", "text": "Check"},
     {"type": "raw_text", "text": "Count"},
     {"type": "raw_text", "text": "vs last wk"}],
    [{"type": "raw_text", "text": "Ready for Dev, no points"},
     {"type": "raw_text", "text": "9/31"},
     {"type": "raw_text", "text": "+5.2"}]
  ]
}
```

**Right-align every numeric column.** Left-aligned numbers of differing width do not compare, which is the entire reason to build a table.

**Add the comparison column.** A table of current values makes the reader remember last week. A `vs last wk` column does the comparing for them, and it is where the lede comes from.

**Do not table three rows of two columns.** That is a list.

**Never put anything load-bearing only in a table cell.** A cell is invisible to every read path — thread matchers, the format audit, search, and the mobile notification all see the `text` fallback, not the grid. A number that matters belongs in the lede as well as the table.

---

## 5. Separator vocabulary — one set, repo-wide

| Glyph | Means | Example |
|---|---|---|
| `·` | between peer facts on one line | `9/31 · 29.0% · +5.2` |
| `—` | between a label and its verdict | `*$175K pipeline added* — target met` |
| `→` | a transition, before to after | `config → feature`, `20 → 15 → 19` |
| `/` | a fraction, only | `9/31` |
| `,` | inside a single field | `$27,420` |

Two separator types per line is the ceiling. `/` is never a fact separator — `Opened 12 / resolved 9 / net +3` reads as three fractions.

**In the two channels that ban the em dash, the label-to-verdict separator is a colon.** `#inbound_leads` (the channel owner's house style) and `#customer-success` (both support scorecards' tone rule) both forbid `—` in the body, so `*$175K pipeline added*: target met`. Everything else in the table is unaffected, and the reserved markers keep their em dashes on every channel — see the scope notes.

**Bullets are `•`.** One character, repo-wide. `-` is retired. It must be a literal `•` and never a leading `*`, which starts a bold span and swallows the line.

**Nesting.** Plain mrkdwn has no nesting — two leading spaces are collapsed by Slack, so a faked second level silently flattens. If a second level is genuinely needed, use a `rich_text_list` with `indent: 1` (verified rendering as `◦` on 2026-08-20), or restructure so it isn't.

---

## 6. Length, by post type

Length is a correctness constraint before it is a style one: Slack silently splits a `chat.postMessage` at roughly 4,000 characters and returns only the **last** chunk's `ts`, so a saved thread anchor points at the tail and every reply to the visible top of the post is invisible to the next run.

This has now bitten twice, and the second time is the more instructive:

- The `hermes-market-intel` digest of 2026-07-31 ran ~5,500 characters. Three approval replies sat unread for two days.
- A fix on 2026-08-21 had to repoint **seven** `acme-call-intel` report threads posted between 07-31 and 08-19, bodies of 4,063 to 5,912 characters, whose recorded `ts` and permalink both anchored to a tail fragment. Every reply left on the visible report was invisible to Step 0. The channel-history self-healing path did not catch it either, because a tail fragment does not match the skill's `*[Deal name] - [meeting type]*` first-line shape — so the fallback that exists precisely for a lost `ts` cannot recover from this particular way of losing one.

| Post type | Target | Hard ceiling |
|---|---|---|
| **Glance** — ticket check, same-day ping, hygiene nudge, run notice | ≤600 rendered chars | 3,800 |
| **Report** — scorecard, readout, digest, brief, card | ≤1,800 rendered chars in the anchor | 3,800 |
| **Overflow** — one thread reply on the anchor | ≤3,800 | 3,800 |

**Rendered, not raw.** Count what a reader sees. `<https://acme-example.atlassian.net/browse/PROJ-123|PROJ-123>` is over 50 raw characters and 8 rendered ones. Measure the rendered string or the limit means nothing — the daily ticket check's own worked example fails its own stated ceiling on raw count and passes on rendered. A skill that states a ceiling without saying which it means (`company-scorecard`'s 3,500, `acme-inbound-leads`'s 3,500) means rendered, from here on.

**3,800 is a wall, not a target.** A report that habitually runs 3,600 characters is a report nobody finishes — and it is one edit away from silently losing its own thread.

**Overflow is one thread reply on the anchor. Never a second top-level message** — two parents means two threads, and half the replies get read by accident.

---

## 7. Zero states and quiet runs

**Collapse the nothings into one line.** A report with seven checks and one finding is one finding and a count, not one finding and six lines of `none`:

```
Two checks moved more than 5pp this week. The other four held.
```

not

```
Carryover: none
Mid-sprint injection: none
Unestimated WIP: none
…
```

Degrading loudly and printing seven zeroes are different things. The loud part is *saying there were seven checks*; it does not require a line each.

**Zero-state filler is banned outright.** A line whose only content is that nothing happened in a section — "no non-dealer accounts confirmed today", "no wrong-person connects today" — does not appear. `bdr-call-coaching` was printing three of these on a one-dial day. Headings may still always appear; their bullets are conditional.

**An unanswered question is asked twice, then it stops.** Repeating the same "worth a check" item daily is the automation restating itself, not new information — `bdr-call-coaching` re-asked one account five days running, each time saying "still no rep read". Cap it and track the count.

**Where a skill has a stay-silent rule, it survives untouched.** Silence at zero (`acme-ticket-daily-check`, `acme-inbound-leads`, `bdr-call-coaching`, `thread-feedback.md`'s no-unhandled-replies case) is correct and this file does not soften it. Likewise a skill that deliberately celebrates a zero (`customer-support-scorecard`'s no-response and stale sections) keeps doing so.

**A metric that could not be computed prints its reason** — the honesty rule is unchanged. What changes is placement: one collapsed block near the end, not a paragraph in the lede slot.

---

## 8. Templates contain no instructions

Every template in a `SKILL.md` is the literal string that gets posted, with variable slots in `{BRACES}`.

- Author-facing conditionals go in prose **outside** the fenced block: "Omit this section when nothing diverged."
- No `· ...` continuation markers, no `(only when X; omit otherwise)`, no bullets that read `- Skip this section entirely if…`.
- If a slot is optional, mark it `{OPTIONAL_…}` and say so in the prose beneath.

---

## 9. Choosing blocks or plain text

Plain `text` mrkdwn is the default and it is often correct. Reach for `blocks` when the post has structure worth carrying.

**Use `blocks` when** the post is a report with ≥3 sections; carries a grid of ≥3×3 like-shaped values; needs provenance de-emphasised rather than merely moved; or needs a real second bullet level.

**Stay in `text` when** the post is a glance; is under ~600 rendered characters; or is a thread reply whose whole content is one corrected line.

### The `text` fallback is not optional, and it is not decoration

`blocks` and `text` are both sent. `text` is what appears in the mobile push, in search, and in every read path — and it is the field a thread matcher can rely on. Three rules follow, and skipping any of them breaks something silently:

1. **`text` carries the skill's byte-stable first-line prefix**, exactly as the matcher expects it, asterisks included. A `header` block is `plain_text` and cannot carry mrkdwn, so the rendered title loses its asterisks; if `text` does not carry the matchable form, Step 0 stops finding the skill's own posts and reports a quiet week. See §1.
2. **`text` is a one-line summary, not a duplicate of the body.** It is the notification, so it should read like one.
3. **Nothing load-bearing lives only inside a `table` block.** The read API returns the surrounding blocks and *not* the table cells — which is why the grid could not be verified from a read-back on 2026-08-20 and needed a human to look on 2026-08-25. The practical consequence: the format-audit routine's live leg cannot inspect table content, so runtime checking covers the prose and never the grid. Keep the number that matters in the lede as well.

Max 50 blocks per message.

The block types worth knowing:

| Block | Does | Use for |
|---|---|---|
| `header` | large bold, plain text only — no mrkdwn | the title |
| `context` | small grey text, mrkdwn | provenance, the "as of" line, section captions |
| `divider` | horizontal rule | between major sections, sparingly |
| `section` | a paragraph of mrkdwn | the lede, prose body |
| `table` | native grid, right-alignable | the grid |
| `rich_text` | real bullets, `indent` levels, `rich_text_quote`, per-run styles | nested lists, quoted asks |

`context` is the single highest-leverage block in this list. It renders provenance in small grey type, which means the meta line stops competing with the content instead of merely moving below it.

**Vendor workflow nodes.** A workflow vendor's `slack_message` integration node reads the `message` key, and its Slack action accepts `blocks` alongside `text`. Everything in this file applies to vendor-authored posts — the Commitment Watchdog digest and the Daily Sales Data Health Monitor included.

---

## 10. Pre-send checklist

Greppable, mechanical, and every item has cost this repo something real. Items 1 and 2 apply to the **API path only** — invert them for a paste-delivered post or a connector fallback.

1. `grep -n '\*\*'` — zero hits. Double-asterisk bold renders visibly.
2. `grep -nE '\[[^]]+\]\('` — zero hits. Markdown links render literally.
3. `grep -nE '<@[A-Z0-9]+\|'` — zero hits. Pipe-labeled mentions render as bracket text, on every path.
4. Is line 2 a fact? If it is a timestamp, a window, or a legend, the lede is missing.
5. Count bold spans. More than one per section means the budget is blown.
6. Does any line carry three or more label:value pairs? That line is a table row.
7. Does every field have a label a reader could say out loud? No bare glyphs.
8. Is every numeric column in every table right-aligned?
9. Rendered length within the target for this post type — links counted as their labels.
10. Is the provenance one line, and last?
11. **If this post uses `blocks`:** does `text` carry the byte-stable first-line prefix the matcher expects, and is nothing load-bearing only inside a table cell?
12. Does the first line still match the skill's thread-discovery prefix, byte for byte?
13. Do all separators come from §5, at most two types per line — and a colon rather than an em dash if this channel bans them?
14. Any zero-state filler lines, or a question already asked twice?
15. Are there any `{BRACES}` or author instructions left in the body?

---

## Scope notes and known collisions

- **The em-dash ban covers two channels, not one.** `#inbound_leads` bans it as the channel owner's house style; `#customer-success` bans it independently through both support scorecards' tone rule and `weekly-support-scorecard`'s Step 11. §5 gives the substitute. The ban does **not** extend to reserved markers (`*Corrected —`, `*Proposed HubSpot change* — <@OWNER_ID>`, `Because: "…" — <@AUTHOR_ID>`, the fallback label) on any channel — stripping the em dash out of a marker breaks the self-skip match, and the next run reads its own output back as fresh human feedback and acts on it.
- **Titles keep their em dashes** even on the two banning channels, because thread discovery matches the prefix byte for byte. `*Customer Support Scorecard — Week of` cannot change. The contradiction is known and the title wins.
- **`gtm-scorecard`'s no-fallback rule is tighter and survives.** A failed bot DM is dropped and reported, never sent as a human. Tighter always wins.
- **This file changes no honesty rule.** Denominators, windows, small-n caveats, printed reasons for uncomputable metrics, no-leaderboard, no-cross-person-content, verbatim-anchored quoting — all unchanged. What changes is where they sit on the page.

## Pickup

`_shared/*.md` has no loader. Claude Code discovers *skills*, and `_shared/` is not one — these files are read only because something tells a run to read them. `write-surfaces.md` declares itself binding on every skill in the repo and has reached 4 of 16, for exactly this reason.

Three channels carry this file, in descending reliability:

1. **The entry prompt** (`prompts/*.md`) — passed to the session directly, so it arrives regardless of working directory. This is the only channel that survives a routine with two repositories attached, where the session starts in the *parent* of both clones. All 16 Slack-posting prompts name this file; `tracker-daily-checkin` does not, because it has no Slack surface.
2. **`CLAUDE.md` at the repo root** — auto-loaded as project memory for any session whose working directory is inside this repo. Covers every single-repo routine and every local `claude` session. Does *not* cover the two-repo market-intel routines, for the same reason `.claude/settings.json` doesn't (see README, *Permission prompts on routine runs*).
3. **A pointer line in each `SKILL.md`**, using the existing convention:

   ```
   **Output format:** per `contracts/slack-format.md` — read it. It governs
   message anatomy, the emphasis budget, tables, separators, and length. Where this file
   and the shared doc disagree, the shared doc wins unless the rule here is tighter.
   ```

   Added per skill as each is next touched, which is how `write-surfaces.md` is being rolled out.

Enforcement is split three ways, and the split matters because each part is blind to what the others catch:

- **A PR check** greps the **fenced templates** of a changed `SKILL.md` for checklist items 1–3. It is a PR check, not a runner — the same category as `canvas-drift.yml`, and explicitly not the kind of workflow the README now forbids. It cannot see runtime output.
- **A scheduled audit routine** reads the last 7 days of the bot's real posts and checks them against this file. This is the only thing that catches a model writing `**bold**` at runtime, which is exactly how the 2026-08-20 card shipped from a clean template. It is blind to table cells (§9) and does not read DMs.
- **The run itself**, performing §10 on its own draft before sending. The only check that happens before a reader sees it.
