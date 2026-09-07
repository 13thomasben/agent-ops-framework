#!/usr/bin/env python3
"""
Offline test suite. No API key, no internet.

    python harnesses/webagent/tests/test_offline.py

Runs the *real* agent loop, the real tool dispatch, and a real Chromium against a
fixture site served on 127.0.0.1, with the Anthropic client replaced by one that
returns scripted tool calls. That covers every moving part except the model's
judgement:

    loop control, cap enforcement, tool dispatch, guardrails, secret handling,
    session persistence, sinks, result shaping

What it deliberately cannot cover is whether Claude *chooses* the right actions
and refuses to invent data — that is model behaviour, not code, and it needs a
real key and a real page. See TESTING.md for that ladder. A green run here means
the machinery is sound, not that the skill is trustworthy.

Worth running after a dependency bump, a Playwright upgrade, or any edit to
agent.py / browser.py / tools.py, because it costs nothing.
"""

from __future__ import annotations

import functools
import glob
import http.server
import json
import os
import socketserver
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from webagent.agent import PRICING, RunResult, _prune_screenshots, run_task  # noqa: E402
from webagent.browser import BrowserSession, BrowserConfig, GuardrailViolation  # noqa: E402
from webagent.sinks import emit  # noqa: E402
from webagent.task import Task  # noqa: E402
from webagent.tools import dispatch, tool_schemas  # noqa: E402


# ---------------------------------------------------------------- fixture site

LOGIN_PAGE = """<!doctype html><title>Lender Portal</title>
<h1>Sign in</h1>
<form method="post" action="/login">
  <input name="username" placeholder="Username">
  <input name="password" type="password" placeholder="Password">
  <button type="submit">Sign in</button>
</form>"""

QUEUE_PAGE = """<!doctype html><title>Application Queue</title>
<h1>Application Queue</h1>
<table>
  <tr><th>ID</th><th>Dealer</th><th>Status</th><th>Rate</th></tr>
  <tr><td>APP-1041</td><td>Ridgeline Equipment</td><td>Awaiting documents</td><td>7.25%</td></tr>
  <tr><td>APP-1042</td><td>Cascade Ag Supply</td><td>Pending review</td><td>n.a.</td></tr>
</table>
<button>Delete application</button>
<a href="/">Sign out</a>"""


class Fixture(http.server.BaseHTTPRequestHandler):
    """Login sets a cookie; the queue 302s back to login without it."""

    def log_message(self, *a):  # keep the test output clean
        pass

    def _send(self, code, body="", headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        if body:
            self.wfile.write(body.encode())

    def do_GET(self):
        # Same markup as /queue but no auth needed, so the destructive-control
        # test doesn't have to log in just to reach a Delete button.
        if self.path.startswith("/open-queue"):
            return self._send(200, QUEUE_PAGE)
        if self.path.startswith("/queue"):
            if "portal_auth=1" in (self.headers.get("Cookie") or ""):
                return self._send(200, QUEUE_PAGE)
            return self._send(302, "", [("Location", "/")])
        return self._send(200, LOGIN_PAGE)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send(
            302,
            "",
            [("Location", "/queue"), ("Set-Cookie", "portal_auth=1; Path=/")],
        )


class Server(socketserver.TCPServer):
    allow_reuse_address = True


def serve() -> tuple[Server, str]:
    srv = Server(("127.0.0.1", 0), Fixture)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


# --------------------------------------------------------------- fake model

def find_chrome() -> str:
    """Whatever Chromium this box has. Playwright's own may not be downloadable."""
    if os.environ.get("WEBAGENT_CHROME_PATH"):
        return os.environ["WEBAGENT_CHROME_PATH"]
    for pat in (
        "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"),
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return ""


class Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Usage:
    def __init__(self, i=1200, o=90):
        self.input_tokens, self.output_tokens = i, o


class Response:
    def __init__(self, content, usage=None, stop_reason="tool_use"):
        self.content, self.usage, self.stop_reason = content, usage or Usage(), stop_reason


def tool_call(name, **args):
    return Response([Block(type="tool_use", id=f"tu_{name}", name=name, input=args)])


class ScriptedClient:
    """Stands in for Anthropic(). Replays `script`, then repeats the last item."""

    def __init__(self, script, usage=None):
        self.script, self.usage = list(script), usage
        self.calls = 0
        self.messages = self
        # Everything the model was ever shown. This is the surface a credential
        # must never reach — it's what lands in a prompt log.
        self.context_seen: list[str] = []

    def create(self, **kw):
        self.calls += 1
        self.context_seen.append(
            json.dumps({"system": kw.get("system"), "messages": kw.get("messages")}, default=str)
        )
        step = self.script[min(self.calls - 1, len(self.script) - 1)]
        r = step(kw) if callable(step) else step
        if self.usage:
            r.usage = self.usage
        return r


# ------------------------------------------------------------------- harness

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))


def make_task(base_url, **over) -> Task:
    raw = dict(
        name="fixture-portal",
        goal="Read the application queue.",
        start_url=f"{base_url}/",
        allowed_domains=["127.0.0.1"],
        secrets=["FIXTURE_USER", "FIXTURE_PASS"],
        max_steps=12,
        result_schema={
            "type": "object",
            "properties": {"applications": {"type": "array", "items": {"type": "object"}}},
            "required": ["applications"],
        },
    )
    raw.update(over)
    t = Task(**raw)
    t.validate()
    return t


def defaults(chrome):
    return {"model": "claude-sonnet-5", "headless": True, "executable_path": chrome}


# ----------------------------------------------------------------- the tests


def test_happy_path(base, chrome):
    """Full loop: navigate, snapshot, fill both secrets, click, snapshot, finish."""
    print("\n[1] happy path — real loop, real browser, scripted model")
    os.environ["FIXTURE_USER"] = "portal-user"
    os.environ["FIXTURE_PASS"] = "correct-horse-battery-staple"

    script = [
        tool_call("browser_navigate", url=f"{base}/"),
        tool_call("browser_snapshot"),
        tool_call("browser_fill_secret", ref=1, secret_name="FIXTURE_USER"),
        tool_call("browser_fill_secret", ref=2, secret_name="FIXTURE_PASS"),
        tool_call("browser_click", ref=3, reason="submit the login form"),
        tool_call("browser_snapshot"),
        tool_call(
            "task_complete",
            result={"applications": [{"id": "APP-1041", "rate": "7.25%"},
                                     {"id": "APP-1042", "rate": "n.a."}]},
            summary="Two applications in the queue.",
        ),
    ]
    task = make_task(base, persist_session=True)
    client = ScriptedClient(script)
    res = run_task(task, defaults(chrome), client=client, verbose=False)

    check("status is completed", res.status == "completed", res.reason)
    check("result came through", len(res.result.get("applications", [])) == 2)
    check("verbatim 'n.a.' preserved end to end",
          res.result.get("applications", [{}, {}])[1].get("rate") == "n.a.")
    check("cost was computed", res.cost_usd > 0)
    check("action_log recorded the login", any("fill_secret" in a for a in res.action_log))
    check("credential value absent from action_log",
          not any("correct-horse" in a for a in res.action_log))
    check("credential value absent from serialised result",
          "correct-horse" not in json.dumps(res.to_dict()))
    # The one that matters most: what the model was actually shown. A leak here
    # ends up in a prompt log, which is the whole reason fill_secret exists.
    leaked = [i for i, c in enumerate(client.context_seen) if "correct-horse" in c]
    check("credential value never entered the model's context", not leaked,
          f"LEAKED into the request at step(s) {leaked} — check fill_secret's return string")
    check("the fill was still confirmed to the model",
          any("FIXTURE_PASS" in c for c in client.context_seen))
    check("session state written", os.path.exists("state/fixture-portal.storage.json"))
    return res


def test_session_reuse(base, chrome):
    """Warm run: the saved cookie should let /queue load without logging in."""
    print("\n[2] session reuse — cookie from run 1 skips the login")
    script = [
        tool_call("browser_navigate", url=f"{base}/queue"),
        tool_call("browser_snapshot"),
        tool_call("task_complete", result={"applications": []}, summary="Read directly."),
    ]
    task = make_task(base, persist_session=True, secrets=[])
    res = run_task(task, defaults(chrome), client=ScriptedClient(script), verbose=False)
    check("status is completed", res.status == "completed", res.reason)
    check("landed on the queue, not bounced to login", res.final_url.endswith("/queue"),
          f"final_url={res.final_url}")


def test_no_session_is_bounced(base, chrome):
    """Control for [2]: without persistence the same script must NOT get in."""
    print("\n[3] control — no saved session, /queue must bounce to login")
    script = [
        tool_call("browser_navigate", url=f"{base}/queue"),
        tool_call("task_complete", result={"applications": []}, summary="."),
    ]
    task = make_task(base, name="fixture-nostate", persist_session=False, secrets=[])
    res = run_task(task, defaults(chrome), client=ScriptedClient(script), verbose=False)
    check("bounced back to the login page", not res.final_url.endswith("/queue"),
          f"final_url={res.final_url}")


def test_guardrails(base, chrome):
    """Blocked actions come back as tool errors the agent can react to."""
    print("\n[4] guardrails — destructive click, off-domain nav, undeclared secret")
    seen = {}

    def spy(kw):
        # Inspect what the model was told after the blocked attempts.
        for m in kw["messages"]:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        txt = str(b.get("content"))
                        if "GUARDRAIL" in txt:
                            seen.setdefault("blocked", []).append(txt)
                        if "not in this task's declared secrets" in txt:
                            seen["undeclared"] = True
        return tool_call("task_failed", reason="blocked as expected")

    script = [
        tool_call("browser_navigate", url=f"{base}/"),
        tool_call("browser_snapshot"),
        tool_call("browser_navigate", url="https://www.wikipedia.org"),
        tool_call("browser_fill_secret", ref=1, secret_name="AWS_SECRET_ACCESS_KEY"),
        spy,
    ]
    task = make_task(base, secrets=["FIXTURE_USER"])
    res = run_task(task, defaults(chrome), client=ScriptedClient(script), verbose=False)

    blocked = " ".join(seen.get("blocked", []))
    check("off-domain navigation refused", "wikipedia.org" in blocked, blocked[:80])
    check("undeclared secret refused", seen.get("undeclared") is True)
    check("task_failed is a first-class outcome", res.status == "failed")
    check("failure carries a reason", bool(res.reason))


def test_destructive_click(base, chrome):
    """The queue page has a 'Delete application' button. It must not fire."""
    print("\n[5] destructive click — 'Delete application' must be refused")
    srv_task = make_task(base, name="fixture-destructive", secrets=[])
    hits = {}

    def spy(kw):
        for m in kw["messages"]:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        if "blocked keyword" in str(b.get("content")):
                            hits["blocked"] = str(b["content"])
        return tool_call("task_failed", reason="destructive control present")

    # Find the Delete button's ref on the live page, then click exactly that.
    found = {}

    def click_delete(kw):
        found["ref"] = _delete_ref(kw)
        return tool_call("browser_click", ref=found["ref"], reason="probe the guard")

    script = [
        tool_call("browser_navigate", url=f"{base}/open-queue"),
        tool_call("browser_snapshot"),
        click_delete,
        spy,
    ]
    res = run_task(srv_task, defaults(chrome), client=ScriptedClient(script), verbose=False)

    # Without this the test can "pass" having clicked some unrelated element.
    check("found the Delete button in the snapshot", found.get("ref", -1) > 0,
          f"ref={found.get('ref')} — snapshot never showed it, so the click proves nothing")
    check("delete click refused at the browser layer", "blocked" in hits,
          "guard did not fire — check DEFAULT_BLOCKED_KEYWORDS")
    check("refusal names the matched keyword", "delete" in hits.get("blocked", "").lower())
    check("run ended without completing", res.status != "completed")


def _delete_ref(kw) -> int:
    """Pull the ref of the 'Delete application' button out of the last snapshot."""
    for m in reversed(kw["messages"]):
        if isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    for line in str(b.get("content")).splitlines():
                        if "Delete application" in line and line.startswith("["):
                            return int(line[1:line.index("]")])
    return -1   # not found — the caller must fail rather than click something else


def test_caps(base, chrome):
    """Steps and dollars each stop a run that would otherwise go forever."""
    print("\n[6] circuit breakers — step cap and cost cap")

    never_finishes = [tool_call("browser_snapshot")]

    t1 = make_task(base, name="fixture-stepcap", secrets=[], max_steps=4)
    r1 = run_task(t1, defaults(chrome), client=ScriptedClient(never_finishes), verbose=False)
    check("step cap aborts the run", r1.status == "aborted", r1.reason)
    check("step cap named in the reason", "step cap" in r1.reason.lower(), r1.reason)
    check("stopped at the cap, not past it", r1.steps == 4, f"steps={r1.steps}")

    t2 = make_task(base, name="fixture-costcap", secrets=[], max_steps=50, max_cost_usd=0.01)
    r2 = run_task(t2, defaults(chrome),
                  client=ScriptedClient(never_finishes, usage=Usage(200_000, 8_000)),
                  verbose=False)
    check("cost cap aborts the run", r2.status == "aborted", r2.reason)
    check("cost cap named in the reason", "cost cap" in r2.reason.lower(), r2.reason)


def test_missing_secret(base, chrome):
    """A run whose secrets aren't set must die before spending anything."""
    print("\n[7] missing secret — fail before browser launch or token spend")
    os.environ.pop("ABSENT_CREDENTIAL", None)
    task = make_task(base, name="fixture-nosecret", secrets=["ABSENT_CREDENTIAL"])
    client = ScriptedClient([tool_call("browser_snapshot")])
    res = run_task(task, defaults(chrome), client=client, verbose=False)
    check("status is error", res.status == "error", res.reason)
    check("names the missing var", "ABSENT_CREDENTIAL" in res.reason)
    check("no tokens spent", res.cost_usd == 0.0 and client.calls == 0)


def test_refusal(base, chrome):
    """A model refusal is surfaced as a failure, not silently retried."""
    print("\n[8] model refusal is surfaced")
    res = run_task(
        make_task(base, name="fixture-refusal", secrets=[]),
        defaults(chrome),
        client=ScriptedClient([Response([Block(type="text", text="no")], stop_reason="refusal")]),
        verbose=False,
    )
    check("status is failed", res.status == "failed", res.reason)
    check("reason mentions the refusal", "refusal" in res.reason.lower())


def test_units():
    """Pieces with no browser in them."""
    print("\n[9] units — pricing, screenshot pruning, schema plumbing, sinks")

    check("every priced model is a current one",
          set(PRICING) == {"claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"},
          str(sorted(PRICING)))

    img = lambda: {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}}
    msgs = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"t{i}", "content": [img()]}]} for i in range(5)]
    _prune_screenshots(msgs)
    live = sum(1 for m in msgs if m["content"][0]["content"][0].get("type") == "image")
    check("only the newest 2 screenshots stay in context", live == 2, f"live={live}")

    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    tools = tool_schemas(allow_secrets=True, result_schema=schema)
    names = [t["name"] for t in tools]
    complete = next(t for t in tools if t["name"] == "task_complete")
    check("result_schema becomes task_complete's contract",
          complete["input_schema"]["properties"]["result"] == schema)
    check("fill_secret only exists when secrets are declared",
          "browser_fill_secret" in names
          and "browser_fill_secret" not in [t["name"] for t in tool_schemas(False, {})])

    payload = RunResult(task="t", status="completed", summary="s",
                        result={"a": 1}, steps=3, cost_usd=0.02).to_dict()
    out = emit(payload, [{"type": "file"}, {"type": "nonexistent-sink"}])
    check("file sink wrote a run artifact", os.path.exists(out.get("file", "")), str(out))
    check("unknown sink degrades, doesn't raise", "unknown" in out.get("nonexistent-sink", ""))
    written = out.get("file", "")
    if os.path.exists(written):
        os.remove(written)


def test_artifacts_are_ignored():
    """The dirs that hold scraped data and live cookies must stay out of git."""
    print("\n[10] run artifacts and session state are gitignored")
    import subprocess

    for rel in ("runs/probe.json", "state/probe.storage.json"):
        p = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").close()
        r = subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT)
        check(f"{rel} is ignored", r.returncode == 0,
              "NOT ignored — scraped data or live cookies could be committed")
        os.remove(p)


# ------------------------------------------------------------------ main

def main() -> int:
    chrome = find_chrome()
    if not chrome:
        print("No Chromium found. Set WEBAGENT_CHROME_PATH or run "
              "`python -m playwright install chromium`.")
        return 2
    print(f"chromium: {chrome}")

    srv, base = serve()
    print(f"fixture:  {base}")
    try:
        for state in glob.glob("state/fixture-*.storage.json"):
            os.remove(state)

        test_happy_path(base, chrome)
        test_session_reuse(base, chrome)
        test_no_session_is_bounced(base, chrome)
        test_guardrails(base, chrome)
        test_destructive_click(base, chrome)
        test_caps(base, chrome)
        test_missing_secret(base, chrome)
        test_refusal(base, chrome)
        test_units()
        test_artifacts_are_ignored()
    finally:
        srv.shutdown()
        for state in glob.glob("state/fixture-*.storage.json"):
            os.remove(state)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAILED: {f}")
        return 1
    print("\nMachinery is sound. This says nothing about whether the model "
          "refuses to fabricate —\nthat needs a real key and a real page. See TESTING.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
