"""Thin HTTP surface for n8n: schedule triggers hit /run/*, the Slack OAuth
webhook forwards consent codes to /oauth/slack/exchange. Stays inside the
compose network; n8n is the only public-facing component."""
from __future__ import annotations

import os
import secrets
import threading

from fastapi import FastAPI, Header, HTTPException

from . import config, credentials, reply_close, store
from .run import daily

app = FastAPI(title="daily-brief", docs_url=None, redoc_url=None)
_lock = threading.Lock()


def _auth(authorization: str | None) -> None:
    expected = f"Bearer {config.env('SERVICE_TOKEN')}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="bad token")


@app.get("/healthz")
def healthz() -> dict:
    with store.conn() as c:
        c.execute("select 1")
    return {"ok": True}


@app.post("/run/daily")
def run_daily(authorization: str | None = Header(default=None)) -> dict:
    _auth(authorization)
    if not _lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="a run is already in progress")
    try:
        failures = daily(config.people(active_only=True))
        return {"ok": failures == 0, "failed_users": failures}
    finally:
        _lock.release()


@app.post("/run/reply-close")
def run_reply_close(authorization: str | None = Header(default=None)) -> dict:
    _auth(authorization)
    run_id = store.start_run("reply_close", None)
    try:
        counts = reply_close.run()
        store.finish_run(run_id, "ok" if counts["processed"] else "no_op", counts)
        return {"ok": True, **counts}
    except Exception as e:
        store.finish_run(run_id, "error", {}, str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/oauth/slack/exchange")
def slack_exchange(payload: dict) -> dict:
    code = payload.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="missing code")
    try:
        result = credentials.slack_exchange_code(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "connected": result["email"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
