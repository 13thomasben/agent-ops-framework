"""scout CLI — the sidecar's front door.

  scout run [--once] [--interval 300]   score new scouted listings, serve buttons
  scout want add "IDEA..."              compile an idea → want file + scout section
  scout want list
  scout status                          every live listing and its state
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .schema import Want
from .state import ListingStore
from .wants import DEFAULT_WANTS_DIR, load_wants, save_want, slugify, upstream_item_section

DEFAULT_STATE_DB = Path.home() / ".scout-state.sqlite3"


def cmd_run(args: argparse.Namespace) -> int:
    from .approvals import telegram_bot
    from .geo import Geo
    from .pipeline import Pipeline, run_loop
    from .scoring.brain import score_listing
    from .sources.upstream_cache import iter_cached_listings

    wants = load_wants(Path(args.wants_dir))
    if not wants:
        print(f"no wants in {args.wants_dir} — add one: scout want add \"...\"")
        return 2
    store = ListingStore(args.state_db)
    geo = Geo()
    if geo.anchor_default:
        print("WARNING: home anchor not set — using downtown DC. "
              "Set SCOUT_HOME_ANCHOR='lat,lon' (or a place name) for a true 10-mile gate.")

    pipeline = Pipeline(store=store, geo=geo, wants=wants,
                        score_fn=score_listing, notify_fn=telegram_bot.send_card)

    offset = 0

    def service_buttons() -> None:
        nonlocal offset
        actions, offset = telegram_bot.poll_callbacks(offset)
        for action, listing_id in actions:
            _handle_button(store, action, listing_id)

    if args.once:
        n = pipeline.run_once(iter_cached_listings(Path(args.cache_dir)))
        service_buttons()
        print(f"processed {n} new listing(s)")
        return 0
    run_loop(pipeline, lambda: iter_cached_listings(Path(args.cache_dir)),
             poll_seconds=args.interval, callbacks_fn=service_buttons)
    return 0


def _handle_button(store: ListingStore, action: str, listing_id: str) -> None:
    from .approvals import telegram_bot
    from .schema import ListingState

    if action == "watch":
        try:
            store.transition(listing_id, ListingState.WATCHING, note="OWNER: watch")
        except Exception:
            pass
        telegram_bot.send_text(f"Watching {listing_id} — I'll re-ping on a price drop.")
    elif action == "kill":
        store.transition(listing_id, ListingState.DEAD, note="OWNER: kill")
        telegram_bot.send_text(f"Killed {listing_id}.")
    elif action == "draft":
        telegram_bot.send_text(_draft_opener(store, listing_id))


def _draft_opener(store: ListingStore, listing_id: str) -> str:
    """Copy-paste opener for OWNER to send themselves — Phase 1 sends nothing."""
    import json as _json

    from .schema import DealVerdict
    from .scoring.brain import MODEL

    row = next((r for r in store.active() if r["id"] == listing_id), None)
    if row is None or not row["verdict_json"]:
        return "No verdict on file for that listing."
    verdict = DealVerdict.model_validate(_json.loads(row["verdict_json"]))
    try:  # pragma: no cover - live path
        import anthropic

        ask = ("; ".join(verdict.missing_info) or "whether it's still available")
        prompt = (f"Write a 2-sentence friendly, non-lowball opening message to a "
                  f"Facebook Marketplace seller of '{row['title']}'. Ask about: {ask}. "
                  f"Do not mention price yet. Sound like a normal person, no emojis.")
        resp = anthropic.Anthropic().messages.create(
            model=MODEL, max_tokens=150,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    except Exception:
        text = (f"Hi! Is the {row['title']} still available? "
                f"Could you tell me {('; '.join(verdict.missing_info) or 'a bit more about its condition')}?")
    return f"Copy-paste opener for {row['title']}:\n\n{text}"


def cmd_want_add(args: argparse.Namespace) -> int:
    from .scoring.brain import compile_want

    idea = " ".join(args.idea)
    print("Compiling want from your idea…")
    spec = compile_want(idea)
    slug = args.slug or spec.get("slug") or slugify(idea)
    want = Want(slug=slug, brief=spec["brief"],
                search_phrases=spec.get("search_phrases", []),
                max_budget=args.budget)
    path = save_want(want, Path(args.wants_dir))
    section = upstream_item_section(want, spec.get("min_price", 20),
                                    spec.get("max_price", 500),
                                    spec.get("antikeywords", []))
    print(f"\nSaved {path}\n\nAdd this to the scout config "
          f"(~/.ai-marketplace-monitor/config.toml) and it starts hunting:\n\n{section}")
    return 0


def cmd_want_list(args: argparse.Namespace) -> int:
    for want in load_wants(Path(args.wants_dir)):
        budget = f" ≤${want.max_budget:.0f}" if want.max_budget else ""
        print(f"{want.slug:20s} bar={want.value_bar:.2f}{budget}  {want.brief[:70]}…")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = ListingStore(args.state_db)
    rows = store.active()
    if not rows:
        print("nothing live")
    for row in rows:
        print(f"{row['state']:18s} ${row['price']:<6.0f} {row['title'][:60]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scout")
    parser.add_argument("--state-db", default=str(DEFAULT_STATE_DB))
    parser.add_argument("--wants-dir", default=str(DEFAULT_WANTS_DIR))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="score new scouted listings; serve buttons")
    p_run.add_argument("--once", action="store_true")
    p_run.add_argument("--interval", type=int, default=300)
    p_run.add_argument("--cache-dir", default=str(Path.home() / ".ai-marketplace-monitor"))
    p_run.set_defaults(fn=cmd_run)

    p_want = sub.add_parser("want", help="manage wants")
    want_sub = p_want.add_subparsers(dest="want_cmd", required=True)
    p_add = want_sub.add_parser("add")
    p_add.add_argument("idea", nargs="+")
    p_add.add_argument("--slug")
    p_add.add_argument("--budget", type=float)
    p_add.set_defaults(fn=cmd_want_add)
    p_list = want_sub.add_parser("list")
    p_list.set_defaults(fn=cmd_want_list)

    p_status = sub.add_parser("status")
    p_status.set_defaults(fn=cmd_status)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
