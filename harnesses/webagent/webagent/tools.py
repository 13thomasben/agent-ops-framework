"""
The tool surface the model sees.

Keep this small. Every tool you add is a new way for a run to go sideways, and
the model reasons better about six good primitives than twenty overlapping ones.
"""

from __future__ import annotations

from typing import Any

from .browser import BrowserSession, GuardrailViolation


def tool_schemas(allow_secrets: bool, result_schema: dict) -> list[dict]:
    tools: list[dict] = [
        {
            "name": "browser_snapshot",
            "description": (
                "Read the current page. Returns the URL, title, a numbered list of "
                "interactive elements, and the visible text. ALWAYS call this "
                "first, and again after any action that changes the page. Element "
                "numbers are only valid until the next action."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "browser_navigate",
            "description": "Go to a URL. Blocked if the domain is not in this task's allowlist.",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        {
            "name": "browser_click",
            "description": "Click an element by its ref number from the most recent snapshot.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Element number, e.g. 7"},
                    "reason": {
                        "type": "string",
                        "description": "One short phrase on why you are clicking this. Used for the audit log.",
                    },
                },
                "required": ["ref", "reason"],
            },
        },
        {
            "name": "browser_type",
            "description": (
                "Type text into an input or textarea by ref. Clears the field first. "
                "Never use this for passwords, API keys, or account numbers — use "
                "browser_fill_secret instead."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer"},
                    "text": {"type": "string"},
                    "submit": {
                        "type": "boolean",
                        "description": "Press Enter afterwards. Default false.",
                    },
                },
                "required": ["ref", "text"],
            },
        },
        {
            "name": "browser_select",
            "description": "Choose an option in a <select> dropdown by ref and option value.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer"},
                    "value": {"type": "string"},
                },
                "required": ["ref", "value"],
            },
        },
        {
            "name": "browser_scroll",
            "description": "Scroll the page to reveal content outside the viewport.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "description": "Pixels. Default 800."},
                },
                "required": ["direction"],
            },
        },
        {
            "name": "browser_back",
            "description": "Go back one page in history.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "browser_wait",
            "description": (
                "Wait for specific text to appear, or wait a fixed number of seconds. "
                "Use when a page is loading asynchronously."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to wait for."},
                    "seconds": {"type": "number", "description": "Fixed wait, max 15."},
                },
                "required": [],
            },
        },
        {
            "name": "browser_screenshot",
            "description": (
                "Take a screenshot of the viewport. Use sparingly — it is expensive. "
                "Only when the text snapshot is genuinely ambiguous, e.g. a chart, a "
                "canvas element, or a visual layout question."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "full_page": {"type": "boolean", "description": "Default false."}
                },
                "required": [],
            },
        },
        {
            "name": "task_complete",
            "description": (
                "Call this when you have gathered everything the task asked for. "
                "The 'result' object must match the schema defined by the task."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "result": result_schema
                    or {"type": "object", "description": "The findings."},
                    "summary": {
                        "type": "string",
                        "description": "Two or three sentences a human can read at a glance.",
                    },
                },
                "required": ["result", "summary"],
            },
        },
        {
            "name": "task_failed",
            "description": (
                "Call this if the task cannot be completed: the page is gone, login "
                "is broken, the data does not exist, or you are blocked. Do not "
                "invent data to avoid failing. A clean failure is far more useful "
                "than a plausible fabrication."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "partial_result": {
                        "type": "object",
                        "description": "Anything you did manage to gather. Optional.",
                    },
                },
                "required": ["reason"],
            },
        },
    ]

    if allow_secrets:
        tools.insert(
            4,
            {
                "name": "browser_fill_secret",
                "description": (
                    "Fill a field with a credential stored in the environment. You "
                    "specify the field ref and the secret's NAME. You will never see "
                    "the value. Use for passwords and any sensitive identifier."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ref": {"type": "integer"},
                        "secret_name": {
                            "type": "string",
                            "description": "Name from the task's declared secrets list.",
                        },
                        "submit": {"type": "boolean"},
                    },
                    "required": ["ref", "secret_name"],
                },
            },
        )

    return tools


TERMINAL_TOOLS = {"task_complete", "task_failed"}


def dispatch(
    session: BrowserSession,
    name: str,
    args: dict[str, Any],
    allowed_secrets: list[str],
) -> tuple[str | list, bool]:
    """
    Execute one tool call.

    Returns (content, is_error). `content` is either a string or a list of
    Anthropic content blocks (used for screenshots).
    """
    try:
        if name == "browser_snapshot":
            return session.snapshot(), False

        if name == "browser_navigate":
            return session.navigate(args["url"]), False

        if name == "browser_click":
            return session.click(int(args["ref"])), False

        if name == "browser_type":
            return (
                session.type_text(
                    int(args["ref"]), args["text"], bool(args.get("submit", False))
                ),
                False,
            )

        if name == "browser_fill_secret":
            secret = args["secret_name"]
            if secret not in allowed_secrets:
                return (
                    f"'{secret}' is not in this task's declared secrets "
                    f"({', '.join(allowed_secrets) or 'none'}). Refused.",
                    True,
                )
            return (
                session.fill_secret(
                    int(args["ref"]), secret, bool(args.get("submit", False))
                ),
                False,
            )

        if name == "browser_select":
            return session.select_option(int(args["ref"]), args["value"]), False

        if name == "browser_scroll":
            return (
                session.scroll(args.get("direction", "down"), int(args.get("amount", 800))),
                False,
            )

        if name == "browser_back":
            return session.go_back(), False

        if name == "browser_wait":
            return (
                session.wait_for(args.get("text"), float(args.get("seconds", 2.0))),
                False,
            )

        if name == "browser_screenshot":
            b64 = session.screenshot_b64(bool(args.get("full_page", False)))
            return (
                [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    }
                ],
                False,
            )

        return f"Unknown tool '{name}'.", True

    except GuardrailViolation as e:
        return f"BLOCKED BY GUARDRAIL: {e}", True
    except Exception as e:
        return (
            f"Tool '{name}' failed: {type(e).__name__}: {e}\n"
            f"The element ref may be stale. Call browser_snapshot and try again.",
            True,
        )
