"""Config loading: roster, weights, filters. Read once per process."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("BRIEF_CONFIG_DIR", Path(__file__).parent.parent / "config"))


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    with open(CONFIG_DIR / name) as f:
        return yaml.safe_load(f) or {}


def roster() -> dict:
    return _load("roster.yaml")


def weights() -> dict:
    return _load("weights.yaml")


def filters() -> dict:
    return _load("filters.yaml")


def people(active_only: bool = False) -> list[dict]:
    d = roster().get("defaults", {})
    out = []
    for p in roster().get("people", []):
        row = {**d, **p}
        if active_only and not row.get("active"):
            continue
        out.append(row)
    return out


def person(key_or_email: str) -> dict:
    for p in people():
        if key_or_email in (p.get("key"), p.get("email")):
            return p
    raise KeyError(f"not in roster: {key_or_email}")


def ops() -> dict:
    return roster().get("ops", {})


def env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None:
        raise RuntimeError(f"missing env var {name} (see .env.example)")
    return v
