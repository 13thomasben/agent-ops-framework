"""
The agent loop.

Model -> tool call -> browser action -> observation -> model. Bounded by three
independent caps (steps, wall clock, dollars) because in practice each one
catches a different failure mode:

  steps   catches the agent looping on a broken element
  time    catches a page that hangs on load
  cost    catches a run that is technically making progress but not worth it
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from anthropic import Anthropic

from .browser import BrowserConfig, BrowserSession
from .task import Task
from .tools import TERMINAL_TOOLS, dispatch, tool_schemas


# USD per million tokens. Verify against
# https://platform.claude.com/docs/en/about-claude/pricing before trusting the
# cost cap with real money.
PRICING = {
    "claude-opus-5":    {"in": 5.00,  "out": 25.00},
    "claude-sonnet-5":  {"in": 2.00,  "out": 10.00},
    "claude-haiku-4-5": {"in": 1.00,  "out": 5.00},
    "claude-fable-5":   {"in": 10.00, "out": 50.00},
}

# Keep at most this many screenshots in context. Older ones are swapped for a
# placeholder — images dominate token cost in a long browser run.
MAX_LIVE_SCREENSHOTS = 2


@dataclass
class RunResult:
    task: str
    status: str                       # completed | failed | aborted | error
    result: dict = field(default_factory=dict)
    summary: str = ""
    reason: str = ""
    steps: int = 0
    elapsed_seconds: float = 0.0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    final_url: str = ""
    action_log: list[str] = field(default_factory=list)
    started_at: str = ""

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "status": self.status,
            "started_at": self.started_at,
            "summary": self.summary,
            "reason": self.reason,
            "result": self.result,
            "metrics": {
                "steps": self.steps,
                "elapsed_seconds": round(self.elapsed_seconds, 1),
                "cost_usd": round(self.cost_usd, 4),
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
            },
            "final_url": self.final_url,
            "action_log": self.action_log,
        }


def _cost(model: str, tin: int, tout: int) -> float:
    p = PRICING.get(model)
    if not p:
        return 0.0
    return (tin / 1_000_000) * p["in"] + (tout / 1_000_000) * p["out"]


def _prune_screenshots(messages: list[dict]) -> None:
    """Replace all but the most recent N images with a text placeholder."""
    positions: list[tuple[int, int, int]] = []
    for mi, msg in enumerate(messages):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for bi, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result" and isinstance(block.get("content"), list):
                for ci, inner in enumerate(block["content"]):
                    if isinstance(inner, dict) and inner.get("type") == "image":
                        positions.append((mi, bi, ci))
    for mi, bi, ci in positions[:-MAX_LIVE_SCREENSHOTS] if len(positions) > MAX_LIVE_SCREENSHOTS else []:
        messages[mi]["content"][bi]["content"][ci] = {
            "type": "text",
            "text": "[earlier screenshot dropped to save context]",
        }


def run_task(
    task: Task,
    defaults: dict[str, Any],
    client: Optional[Anthropic] = None,
    verbose: bool = True,
) -> RunResult:
    client = client or Anthropic()

    model = task.model or defaults.get("model", "claude-sonnet-5")
    max_steps = task.max_steps or defaults.get("max_steps", 40)
    timeout_s = task.timeout_seconds or defaults.get("timeout_seconds", 600)
    max_cost = task.max_cost_usd or defaults.get("max_cost_usd", 1.00)
    headless = task.headless if task.headless is not None else defaults.get("headless", True)

    started = time.time()
    res = RunResult(
        task=task.name,
        status="error",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )

    missing = task.missing_secrets()
    if missing:
        res.status = "error"
        res.reason = f"Missing environment secrets: {', '.join(missing)}"
        return res

    bcfg = BrowserConfig(
        headless=headless,
        cdp_url=defaults.get("cdp_url") or None,
        executable_path=(
            os.environ.get("WEBAGENT_CHROME_PATH")
            or defaults.get("executable_path")
            or None
        ),
        storage_state_path=task.storage_state_path,
        nav_timeout_ms=int(defaults.get("nav_timeout_ms", 30_000)),
        action_timeout_ms=int(defaults.get("action_timeout_ms", 10_000)),
    )

    tools = tool_schemas(allow_secrets=bool(task.secrets), result_schema=task.result_schema)
    system = task.system_prompt()
    messages: list[dict] = [{"role": "user", "content": task.initial_message()}]

    session = BrowserSession(bcfg, task.allowed_domains, task.blocked_keywords)

    try:
        session.start()

        for step in range(1, max_steps + 1):
            res.steps = step
            elapsed = time.time() - started

            if elapsed > timeout_s:
                res.status = "aborted"
                res.reason = f"Wall-clock timeout after {int(elapsed)}s (cap {timeout_s}s)"
                break
            if res.cost_usd > max_cost:
                res.status = "aborted"
                res.reason = f"Cost cap hit: ${res.cost_usd:.3f} > ${max_cost:.2f}"
                break

            _prune_screenshots(messages)

            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
            )

            res.input_tokens += response.usage.input_tokens
            res.output_tokens += response.usage.output_tokens
            res.cost_usd = _cost(model, res.input_tokens, res.output_tokens)

            if getattr(response, "stop_reason", None) == "refusal":
                res.status = "failed"
                res.reason = "Model declined the request (stop_reason: refusal)."
                break

            messages.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                text = " ".join(b.text for b in response.content if b.type == "text")
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You did not call a tool. Continue working, or call "
                            "task_complete / task_failed to finish."
                        ),
                    }
                )
                if verbose and text:
                    print(f"  [{step}] (no tool) {text[:150]}")
                continue

            tool_results = []
            terminal: Optional[tuple[str, dict]] = None

            for tu in tool_uses:
                args = tu.input or {}
                if verbose:
                    detail = args.get("reason") or args.get("url") or args.get("text") or ""
                    print(f"  [{step}] {tu.name} {str(detail)[:70]}")

                if tu.name in TERMINAL_TOOLS:
                    terminal = (tu.name, args)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": "Recorded. Run ending.",
                        }
                    )
                    continue

                content, is_error = dispatch(session, tu.name, args, task.secrets)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": content,
                        **({"is_error": True} if is_error else {}),
                    }
                )

            messages.append({"role": "user", "content": tool_results})

            if terminal:
                name, args = terminal
                if name == "task_complete":
                    res.status = "completed"
                    res.result = args.get("result", {}) or {}
                    res.summary = args.get("summary", "")
                else:
                    res.status = "failed"
                    res.reason = args.get("reason", "unspecified")
                    res.result = args.get("partial_result", {}) or {}
                break
        else:
            res.status = "aborted"
            res.reason = f"Hit step cap ({max_steps}) without finishing."

        try:
            res.final_url = session.page.url if session.page else ""
        except Exception:
            pass
        res.action_log = list(session.action_log)

    except Exception as e:
        res.status = "error"
        res.reason = f"{type(e).__name__}: {e}"
        try:
            res.action_log = list(session.action_log)
        except Exception:
            pass
    finally:
        session.stop()
        res.elapsed_seconds = time.time() - started

    return res
