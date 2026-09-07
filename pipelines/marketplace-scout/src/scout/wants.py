"""Want files: one TOML per thing OWNER is hunting (configs/wants/*.toml).

A want's `brief` is plain English — the whole point is that OWNER types an idea
("a desk around 60in wide, 28-30in tall, tasteful wood, sturdy") and the
system does the rest. `cli.py want add` compiles a brief into search phrases +
an upstream [item.<slug>] section via the model; this module just loads/saves.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover - py310 fallback
    import tomli as tomllib  # type: ignore

from .schema import Want

DEFAULT_WANTS_DIR = Path("configs") / "wants"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40] or "want"


def load_want(path: Path) -> Want:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    data.setdefault("slug", path.stem)
    return Want.model_validate(data)


def load_wants(wants_dir: Path = DEFAULT_WANTS_DIR) -> list[Want]:
    """All active wants, sorted by slug. Missing dir → empty list."""
    if not wants_dir.is_dir():
        return []
    wants = [load_want(p) for p in sorted(wants_dir.glob("*.toml"))]
    return [w for w in wants if w.active]


def save_want(want: Want, wants_dir: Path = DEFAULT_WANTS_DIR) -> Path:
    """Write a want file. TOML-escapes via triple-quoted brief."""
    wants_dir.mkdir(parents=True, exist_ok=True)
    path = wants_dir / f"{want.slug}.toml"
    brief = want.brief.replace("'''", "'​''")  # never terminate the literal
    phrases = ", ".join(f"'{p}'" for p in want.search_phrases)
    budget = f"max_budget = {want.max_budget}\n" if want.max_budget else ""
    path.write_text(
        f"slug = '{want.slug}'\n"
        f"value_bar = {want.value_bar}\n"
        f"{budget}"
        f"search_phrases = [{phrases}]\n"
        f"active = {'true' if want.active else 'false'}\n"
        f"brief = '''\n{brief}\n'''\n",
        encoding="utf-8",
    )
    return path


def upstream_item_section(want: Want, min_price: int, max_price: int,
                          antikeywords: list[str] | None = None) -> str:
    """The [item.<slug>] block to paste/write into the upstream scout config.

    Scout mode: upstream does search + cache only (no [ai.*] sections), so this
    section needs no description — the sidecar's brain does all judging.
    """
    phrases = ", ".join(f"'{p}'" for p in want.search_phrases)
    anti = ", ".join(f"'{a}'" for a in (antikeywords or []))
    lines = [
        f"[item.{want.slug}]",
        f"search_phrases = [{phrases}]",
        f"min_price = {min_price}",
        f"max_price = {max_price}",
    ]
    if anti:
        lines.append(f"antikeywords = [{anti}]")
    return "\n".join(lines) + "\n"
