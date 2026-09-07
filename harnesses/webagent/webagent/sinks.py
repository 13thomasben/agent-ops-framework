"""
Where results go after a run.

Every sink takes the same RunResult dict. Add your own by writing a function
here and registering it in DISPATCH — that is the extension point for pushing
into a workflow vendor, n8n, Jira, or anything else you already run.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any


def _post_json(url: str, payload: dict, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return f"{r.status}"


def sink_stdout(result: dict, cfg: dict) -> str:
    print(json.dumps(result, indent=2, default=str))
    return "printed"


def sink_file(result: dict, cfg: dict) -> str:
    directory = cfg.get("dir", "runs")
    os.makedirs(directory, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(directory, f"{result['task']}-{stamp}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    return path


def sink_slack_webhook(result: dict, cfg: dict) -> str:
    """
    Post a compact summary to a Slack incoming webhook.
    Set the URL via env var name in `url_env`, not inline.
    """
    url = os.environ.get(cfg.get("url_env", "SLACK_WEBHOOK_URL"))
    if not url:
        return "skipped (no webhook url in env)"

    status = result["status"]
    icon = {"completed": ":white_check_mark:", "failed": ":x:"}.get(status, ":warning:")
    m = result["metrics"]

    body = result.get("summary") or result.get("reason") or "(no summary)"
    lines = [
        f"{icon} *{result['task']}* — {status}",
        body,
        f"_{m['steps']} steps · {m['elapsed_seconds']}s · ${m['cost_usd']}_",
    ]

    payload: dict[str, Any] = {"text": "\n".join(lines)}

    if cfg.get("include_result") and result.get("result"):
        blob = json.dumps(result["result"], indent=2, default=str)
        if len(blob) < 2800:
            payload["text"] += f"\n```{blob}```"

    try:
        return _post_json(url, payload)
    except Exception as e:
        return f"error: {e}"


def sink_webhook(result: dict, cfg: dict) -> str:
    """Generic POST — point this at n8n, a workflow-vendor trigger, or your own API."""
    url = os.environ.get(cfg["url_env"]) if cfg.get("url_env") else cfg.get("url")
    if not url:
        return "skipped (no url)"
    try:
        return _post_json(url, result)
    except Exception as e:
        return f"error: {e}"


DISPATCH = {
    "stdout": sink_stdout,
    "file": sink_file,
    "slack_webhook": sink_slack_webhook,
    "webhook": sink_webhook,
}


def emit(result: dict, sinks: list[dict]) -> dict[str, str]:
    """Run every configured sink. A failing sink never fails the run."""
    out: dict[str, str] = {}
    for spec in sinks or [{"type": "file"}]:
        kind = spec.get("type")
        fn = DISPATCH.get(kind)
        if not fn:
            out[str(kind)] = "unknown sink type"
            continue
        try:
            out[kind] = fn(result, spec)
        except Exception as e:
            out[kind] = f"error: {e}"
    return out
