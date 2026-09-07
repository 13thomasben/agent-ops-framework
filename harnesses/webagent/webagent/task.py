"""
Task definitions.

A task is a YAML file. It is the contract between you and the agent: what to do,
where it may go, when to give up, and what shape the answer must take.

Keep tasks declarative. If you find yourself wanting to write procedure into the
`goal`, that is a signal the target site is stable enough to script with plain
Playwright instead — which will be cheaper and more reliable.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml


REQUIRED = ("name", "goal", "start_url", "allowed_domains")

# Clicks on elements whose label matches these are refused unless the task
# explicitly opts in via `allow_destructive: true`. Deliberately blunt.
DEFAULT_BLOCKED_KEYWORDS = [
    "delete", "remove", "cancel subscription", "close account", "deactivate",
    "pay now", "place order", "confirm payment", "submit payment", "buy now",
    "checkout", "transfer funds", "wire", "send money", "approve",
    "publish", "send invoice", "terminate",
]


@dataclass
class Task:
    name: str
    goal: str
    start_url: str
    allowed_domains: list[str]

    description: str = ""
    model: Optional[str] = None
    max_steps: Optional[int] = None
    timeout_seconds: Optional[int] = None
    max_cost_usd: Optional[float] = None

    result_schema: dict = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    allow_destructive: bool = False
    extra_blocked_keywords: list[str] = field(default_factory=list)

    headless: Optional[bool] = None
    persist_session: bool = False
    schedule: str = ""          # informational: cron string for your scheduler
    sinks: list[dict] = field(default_factory=list)
    notes: str = ""             # free-text hints handed to the model

    _path: str = ""

    # ---------------- loading ----------------

    @classmethod
    def from_file(cls, path: str) -> "Task":
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: top level must be a mapping")

        missing = [k for k in REQUIRED if not raw.get(k)]
        if missing:
            raise ValueError(f"{path}: missing required field(s): {', '.join(missing)}")

        known = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(
                f"{path}: unknown field(s): {', '.join(sorted(unknown))}. "
                f"Valid fields: {', '.join(sorted(known))}"
            )

        task = cls(**{k: v for k, v in raw.items() if k in known})
        task._path = path
        task.validate()
        return task

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", self.name):
            raise ValueError(
                f"task name '{self.name}' must be lowercase alphanumeric with . _ -"
            )
        if not self.allowed_domains:
            raise ValueError("allowed_domains must not be empty")
        if "*" in self.allowed_domains and len(self.allowed_domains) > 1:
            raise ValueError("allowed_domains: '*' cannot be combined with other entries")
        if self.result_schema and self.result_schema.get("type") != "object":
            raise ValueError("result_schema must be a JSON Schema object at the top level")
        for s in self.secrets:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", s):
                raise ValueError(
                    f"secret '{s}' should be an ENV_VAR_STYLE name, not a literal value"
                )

    def missing_secrets(self) -> list[str]:
        return [s for s in self.secrets if os.environ.get(s) is None]

    @property
    def blocked_keywords(self) -> list[str]:
        if self.allow_destructive:
            return list(self.extra_blocked_keywords)
        return DEFAULT_BLOCKED_KEYWORDS + list(self.extra_blocked_keywords)

    @property
    def storage_state_path(self) -> Optional[str]:
        if not self.persist_session:
            return None
        return os.path.join("state", f"{self.name}.storage.json")

    # ---------------- prompt construction ----------------

    def system_prompt(self) -> str:
        domains = ", ".join(self.allowed_domains)
        lines = [
            "You are a browser agent. You operate a real Chromium browser through "
            "tools, the way a careful human would: look at the page, decide, act, "
            "look again.",
            "",
            "## How to operate",
            "1. Call browser_snapshot before your first action and after every "
            "action that changes the page. Element refs go stale immediately.",
            "2. Take one action at a time. Do not guess a ref you have not seen in "
            "the current snapshot.",
            "3. If an action fails twice the same way, change approach — scroll, go "
            "back, try a different element, or use a different entry point.",
            "4. Read the page text before concluding something is absent. Content "
            "below the fold needs a scroll and a fresh snapshot.",
            "",
            "## Honesty rules (these matter more than finishing)",
            "- Report only what you actually observed on the page. Never fill gaps "
            "from prior knowledge or plausible inference.",
            "- If a value is not present, say so. Do not approximate it.",
            "- If you cannot complete the task, call task_failed with a specific "
            "reason. A clean failure is a useful result. A fabricated success is "
            "worse than useless — it will be trusted.",
            "- If you hit a login wall, CAPTCHA, or paywall you cannot legitimately "
            "pass, stop and call task_failed. Do not attempt to circumvent it.",
            "",
            "## Boundaries",
            f"- You may only browse: {domains}",
            "- Do not submit forms, send messages, make purchases, or change any "
            "state unless the goal explicitly asks for it.",
        ]
        if not self.allow_destructive:
            lines.append(
                "- Destructive-looking controls (delete, pay, submit, approve, "
                "publish) are blocked. Do not try to route around the block."
            )
        if self.secrets:
            lines.append(
                f"- Credentials available via browser_fill_secret: "
                f"{', '.join(self.secrets)}. You will never see their values."
            )
        lines += [
            "",
            "## Finishing",
            "Call task_complete with a result object matching the required schema, "
            "plus a short human-readable summary. Do not pad the summary.",
        ]
        if self.notes:
            lines += ["", "## Task-specific notes", self.notes.strip()]
        return "\n".join(lines)

    def initial_message(self) -> str:
        parts = [f"# Goal\n{self.goal.strip()}", f"\n# Starting point\n{self.start_url}"]
        if self.result_schema:
            import json

            parts.append(
                "\n# Required result shape\n```json\n"
                + json.dumps(self.result_schema, indent=2)
                + "\n```"
            )
        parts.append(
            "\nBegin by navigating to the starting point, then take a snapshot."
        )
        return "\n".join(parts)


def load_all(tasks_dir: str = "tasks") -> dict[str, Task]:
    out: dict[str, Task] = {}
    if not os.path.isdir(tasks_dir):
        return out
    for fn in sorted(os.listdir(tasks_dir)):
        if not fn.endswith((".yaml", ".yml")):
            continue
        task = Task.from_file(os.path.join(tasks_dir, fn))
        if task.name in out:
            raise ValueError(f"duplicate task name '{task.name}' in {fn}")
        out[task.name] = task
    return out
