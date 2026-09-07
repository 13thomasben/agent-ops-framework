# Phase 1 design — the generalized deal brain (July 2026)

## What OWNER asked for

Any item, small or large — not just furniture. Give the system an *idea* of a
want in plain English; it searches, actually looks at listings (photos, not
just filters), and only pings when something is a real deal that's either
close to home or worth its delivery cost. No rigid bounds — model judgment
inside code-enforced money/geo rails.

## Architecture decision: sidecar, not fork

The upstream monitor keeps doing the one dangerous job — touching Facebook —
exactly as before (headed browser, real profile, jittered 30-60 min polls).
In **scout mode** (`configs/upstream-scout.toml`) it runs with no AI and no
notification channels: it just searches and caches every listing's details
(diskcache at `~/.ai-marketplace-monitor`, one primary photo per listing).

The **sidecar** (`scout run`) polls that local cache every ~5 minutes
(zero Facebook traffic), and for each new (listing, price) pair:

```
upstream cache ─► geo.py (gazetteer→Nominatim: miles from home)
              ─► transport.py (sedan $25 / suv $45 / two-person = Lugg math;
                               $0 self-pickup when close; unknown ≠ close)
              ─► scoring/brain.py (Sonnet w/ photo: soft-fit vs the want brief,
                               quality, fair value, transport class, scam flags)
              ─► pipeline.gates (CODE decides: no scam flags; all-in ≤
                               value_bar × fair value; ≤ budget; fit ≥ 6; unseen)
              ─► telegram card: photo + verdict + [Watch] [Kill] [Draft opener]
```

Why sidecar won: zero fork maintenance as upstream evolves, no duplicate
scraping, clean AGPL separation (upstream stays an unmodified pip dependency),
and the brain/notifier is 100% ours to iterate on.

## Soft fit, hard money

The want's `brief` is the spec — dimensions and style are *targets with human
tolerances*, and the model explains its reasoning in `fit_notes`. But the
model's arithmetic is advisory only: `pipeline.apply_money_math` recomputes
delivery cost, all-in, and value ratio in code from the model's transport
class + geo's distance, and `gates()` makes the notify decision. Distance
unknown is priced like a 12-mile mover run and never counts as "close."

## Wants

One TOML per want in `configs/wants/` (brief, value_bar, budget, phrases).
`scout want add "60 inch wood desk, sturdy, tasteful"` uses the model to
compile an idea into a want file + a ready-to-paste `[item.X]` scout section —
that's the "give it an idea" interface. The upstream item name is the join key
(`listing.want_slug`), so multiple wants run concurrently without cross-talk.

## Known limits (accepted for Phase 1)

- **One photo per listing** (that's all upstream caches). The card's "Draft
  opener" asks the seller for what's missing; the Phase 2 Messenger driver
  will pull full galleries once it owns the browser session.
- **Geo is text-based**: gazetteer covers the DMV, Nominatim handles the rest,
  and unresolvable locations get mover-math. Precision improves when OWNER sets
  `SCOUT_HOME_ANCHOR` (lat,lon or place/ZIP).
- **Draft opener is copy-paste** — zero automated seller contact in Phase 1,
  by design (account safety; see CLAUDE.md hard rules).

## Acceptance (unchanged from CLAUDE.md, now concrete)

New cache entry → validated verdict + card on the phone within one sidecar
poll (≤5 min after upstream's crawl finds it); every notification passed the
code gates; `pytest -q` green with no network.
