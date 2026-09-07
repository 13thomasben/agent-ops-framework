# Process: adding an enduring skill or routine

This is the repeatable checklist for putting a new skill into this repo so a
Claude Code routine can call it. It's written so **either a human or another
Claude account** can follow it.

## Rule of thumb

Whenever you build something you want to run again later — an "enduring" skill
or a scheduled routine — it does **not** stay in the chat where you made it.
Chat/session environments are temporary. The durable copy lives **here**, in
`skills/`, and the routine points at this repo.

## Steps to add a new skill

1. **Pick a short, lowercase, hyphenated name**, e.g. `acme-call-intel`.
   This becomes the folder name and the skill identifier.

2. **Create the folder and file:**
   ```
   skills/<name>/SKILL.md
   ```
   Add a `scripts/` subfolder alongside it if the skill needs code.

3. **Write `SKILL.md` with frontmatter.** Minimum required:
   ```markdown
   ---
   name: <name>
   description: One or two sentences on what it does AND when to use it.
                This is what makes Claude pick the skill — be specific.
   ---

   # <Title>
   Concise instructions. Keep it tight.
   ```

4. **Keep secrets out.** Reference API keys via environment variables
   (e.g. `FIREFLIES_API_KEY`), set on the routine — never in the file.

   **If the skill posts to Slack**, it posts as `@bot`, not as a person:
   Slack Web API calls with the bot token in `SLACK_BOT_TOKEN`, not
   `slack_send_message` (that writes as the connector's user — it is the
   labeled fallback only). Reads stay on the
   Slack connector. Follow `contracts/slack-dispatch.md` and set
   `SLACK_BOT_TOKEN` in the routine's environment variables.

   **And it follows the output format contract**,
   `contracts/slack-format.md` — message anatomy (title, lede, body,
   ask, provenance, in that order), the emphasis budget, when a grid becomes a
   `table` block, the separator set, and the length ceiling for the post's type.
   Put the skill's literal template in its `SKILL.md` as a fenced block with
   variable slots in `{BRACES}` and **no author instructions inside the fence** —
   a conditional like "omit when nothing diverged" goes in prose underneath, or a
   literal renderer posts it. Then run that file's §10 checklist against a real
   draft before the first live post: three of its twelve items catch syntax that
   renders as visible punctuation, and each of those has reached a reader at least
   once.

5. **If the skill delivers into a Slack channel, write its canvas.** Every channel a skill posts into carries a channel canvas describing it in plain language for the people who *read* the output. **Three sections, in this order: agent description, how it works, how to interact with it** — then *Who to ask*, which is just the Owner. Around 50 lines; no limits or gaps sections. Sources live in `docs/agent-canvases/`, one per channel, and the folder README carries the conventions, the format rules and the publish call.

   Register the channel in `docs/agent-canvases/channels.json` — that manifest is what the coverage table, the publish step, and the drift check all read. A skill with no Slack delivery of its own (a building block like `webagent`) goes in the manifest's `no_canvas` list with the reason.

6. **Register the skill's write surfaces, and run the gate.** Before it ships, every
   write the skill can make into a system outside this repo gets classified on the
   four axes in `contracts/write-surfaces.md` — reversibility, record
   ownership, **audience**, and **attribution** — and looked up in that file's surface
   register. Put the resulting table in the skill's `SKILL.md` as a **Write surfaces**
   block.

   Two of those axes exist because of a 2026-08-19 incident: an automation wrote
   30 comments onto 24 customer-facing service-desk tickets over four weeks, and the
   guardrail of the day passed it — because it asked whether the write was reversible
   and whose record it touched, and never asked who could see it or whose name was on
   it. Enumerate rarely-executed paths too: the second-worst finding in that incident
   sat in a dedupe branch that no review of the reply loop would ever have reached.

   The short version of the gate, if you read nothing else: **if this write is wrong,
   who finds out first — us, or a customer?** A surface that isn't in the register
   counts as customer-visible and the write does not ship.

7. **Commit and push to the default branch** (`main`).

8. **Link the routine to this repo** (once per routine): in Claude Code →
   Routines → the routine → repository / environment settings, select
   `acme-skills`. If the routine needs packages installed, add them in the
   routine's **setup script**; put secrets in the routine's **environment
   variables** (note: env vars are NOT visible inside the setup script — use
   them from the skill steps instead).

   **Do not add a permission installer to the setup script.** Earlier revisions of
   this step told you to, via `scripts/install-routine-permissions.sh`. That script
   has been deleted and the line should be removed from any environment that still
   carries it — it is a no-op for the problem it claimed to solve. Nothing in this
   repo pre-approves connector calls: the proxy raises its approval card *after* the
   local permission layer passes, with always-allow deliberately suppressed and the
   approval pinned to the call's arguments. README, *Permission prompts on routine
   runs*, carries the verified mechanism and the evidence.

   What this means when you wire a routine: **assume every connector call it makes
   can stall an unattended run.** Prefer a token-and-HTTPS path over a connector
   wherever one exists — `_shared/slack-dispatch.md` for Slack,
   `_shared/hubspot-rest.md` for HubSpot — and treat a connector-only read as a
   known liability to note in the skill's degrade-loudly path.

   One thing worth keeping from the old text, because it is still true and still
   bites: **anything you do put in a setup script must be fail-soft.** A setup
   script that exits non-zero aborts the run before Claude Code starts — the
   container builds, the repo clones, and then nothing happens at all. A bare
   `bash <missing path>` returns 127 and does exactly that (it has happened).

   **Then verify it, in a session on that environment** — this step was assumed
   done for three weeks and was not, and the cost was seven scheduled runs that
   parked on an approval prompt nobody answered:

   ```sh
   cat ~/.claude/settings.json | jq -r '.permissions.allow[] | select(startswith("mcp__"))'
   ```

   No output or no file means the allowlist is not in force, whatever the setup
   script says. The routine's own `allowed_tools` list covers built-in tools only
   and looks healthy either way, so it is not evidence. When a run does stall,
   `get_session` on its session names the tool it is parked on.

9. **Test:** trigger the routine manually once and confirm it finds and runs the
   skill.

## Changing an existing skill — update its canvas in the same change

**A skill and its channel canvas ship together.** The canvas is what the people
reading the output believe about the automation, so a canvas that has drifted is
worse than no canvas: they act on it. Set by the CEO 2026-08-11.

`docs/agent-canvases/channels.json` maps every skill to the canvas(es) that
describe it. Before merging a change to a `SKILL.md`, ask whether it moved any of
the four things a reader relies on:

| If the change moves… | …the canvas needs |
|---|---|
| **Cadence** — how often it runs, or the window it covers | the tempo line, and anything that quotes the window |
| **Delivery surface** — which channel, who gets tagged, what goes to a DM | the opening lines, and the coverage table in `channels.json` |
| **Thresholds and rules** — what makes something appear, what gets suppressed | the rules section, and any worked example |
| **Write authority** — what it changes automatically vs. proposes, and the rails | the "how to use it" table and the propose/approve description. **Also re-run the write-surface gate** (step 6) and update the skill's Write surfaces block — a change that widens *what* or *where* a skill writes is exactly the change that needs the audience and attribution axes re-checked |
| **Output shape** — the template, what leads, what gets bold, whether it threads overflow | any worked example in the canvas, and a re-read of `_shared/slack-format.md`. **If the first line changed, stop** — thread discovery matches on that prefix byte for byte, so a retitle is a matcher change and breaks every reply loop on prior posts |

Two more that are easy to forget:

- **A limit that gets fixed comes out of the canvas in the same change that fixes
  it.** Canvases don't carry a limits section, but the few that survive inline —
  Fireflies name accuracy, what a capture flag means — describe things somebody is
  presumably working on. A stale one makes readers distrust what's still true.
- **A change to a shared contract** (`contracts/*.md`) touches every
  canvas, because those rails — the propose/approve protocol, the blast-radius
  ladder, the posting identity — are described in all of them. A change to
  `slack-format.md` additionally touches every worked example in every canvas,
  since those quote the output verbatim.

A wording fix, a clarified rail, or a pinned ID usually moves none of the four and
needs no canvas edit. `.github/workflows/canvas-drift.yml` leaves a non-blocking
annotation on any PR that changes a skill without touching its canvas, naming the
file to look at. It is a reminder, not a gate — deciding "nothing a reader relies
on moved" is a legitimate answer to it.

Publishing an updated canvas is a re-publish from the source file, never an edit
in the Slack canvas itself — see `docs/agent-canvases/README.md`.

## Commit signing in Claude Code cloud sessions (read before "fixing" it)

Commits made from Claude Code's managed cloud containers are **already signed
and show Verified on GitHub**. Automated hooks and past sessions have
repeatedly mis-diagnosed this as broken; here is the actual setup so nobody
loops on it again.

How it works in these containers:

- Git is configured with `commit.gpgsign=true`, `gpg.format=ssh`, and
  `gpg.ssh.program` pointing at the environment's own signing shim
  (`/tmp/code-sign` → the environment-runner binary). The shim signs each
  commit with a managed ed25519 key whose public half is registered with
  GitHub for the `claude` account (its vendor noreply address), so GitHub
  verifies these signatures.

Known red herrings — none of these mean commits are unsigned:

- `/home/claude/.ssh/commit_signing_key.pub` may be an **empty (0-byte)
  file**. The shim does not read it; signing works regardless.
- `git log --show-signature` reports "No signature" or errors. Local
  verification is impossible in the container: `ssh-keygen` is not
  installed and the shim only implements `-Y sign`, not `-Y verify`.
  This is a display limitation, not a signing failure.

How to actually check a commit's signature status — ask GitHub, the only
source of truth here:

```
curl -sS https://api.github.com/repos/<owner>/acme-skills/commits/<sha> \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['commit']['verification'])"
```

`{"verified": true, "reason": "valid", ...}` means the badge is green. Do
**not** amend/force-push commits to "re-sign" them based on local
`--show-signature` output alone.

## Handoff prompt for the other Claude account

Paste something like this into the account that already has the working skill:

> I have a skill called `<name>` (the instructions and code) built in this
> session. I need it committed to my GitHub repo `acme-skills` at
> `skills/<name>/SKILL.md` (plus any scripts under
> `skills/<name>/scripts/`), so my scheduled Claude Code routine can
> load it. Please output the final `SKILL.md` (with `name` + `description`
> frontmatter) and each script as separate files with their exact repo paths, so
> I can drop them into the repo. Keep all API keys out of the files and reference
> them as environment variables instead.

Then either commit those files yourself, or hand them back here and they'll be
added to the repo.
