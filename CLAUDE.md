# acme-skills

Durable Claude Code skills for Acme's scheduled routines. Skills live in `skills/`; entry prompts in `prompts/`. `PROCESS.md` is the checklist for adding or changing one.

## Shared contracts — read the ones your task touches

Six files in `contracts/` are canonical and outrank an individual `SKILL.md`, except where the skill's own rule is *tighter* (tighter always wins):

| File | Governs |
|---|---|
| `slack-dispatch.md` | **how** a skill posts — `@bot` identity, token, recipes, failure modes |
| `hubspot-rest.md` | **how** a skill reads HubSpot — REST + private-app token, connector as labeled fallback. Inert until `HUBSPOT_PRIVATE_APP_TOKEN` is provisioned; changes no write authority *(not included in this public showcase)* |
| `slack-format.md` | **what the reader sees** — message anatomy, emphasis budget, tables, separators, length |
| `thread-feedback.md` | **what a skill does about replies** — categories, blast-radius ladder, propose/approve |
| `write-surfaces.md` | **whether a skill may write at all** — the four-axis gate |
| `ticket-taxonomy.md` | how a service-desk ticket gets classified *(not included in this public showcase)* |

**If you are writing or editing anything a skill posts to Slack, read `slack-format.md` first.** It is the newest of these and the least likely to be reflected already in the `SKILL.md` you are editing. Its §10 checklist is twelve mechanical checks — run them against the actual draft before it posts. Three of them (`**bold**`, `[label](url)`, `<@U…|Name>`) catch syntax that renders as visible punctuation through the raw API, and each has reached a reader at least once.

Canvases are a different surface with inverted syntax — `[label](url)`, `![](@U…)`, real markdown tables, `**bold**`. They follow `docs/agent-canvases/README.md`, never `slack-format.md`.

## Standing rules

- **Never post as a human.** Writes go out as `@bot` with `$SLACK_BOT_TOKEN`. `slack_send_message` and friends write as the connector's human user and are the labeled fallback only, with the label.
- **Secrets are env vars.** Never inline, never echoed, never committed.
- **A number carries its denominator and window, or it carries the reason there is no number.** Repo-wide, inherited from `sprint-integrity-readout`.
- **Silence is a valid output** wherever a skill says so. Do not invent an all-clear post.
