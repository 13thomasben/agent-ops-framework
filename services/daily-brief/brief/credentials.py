"""Credential broker — the seam that de-risked the June auth gate.

Every pull asks THIS module for a token for (source, user). The hybrid decision
lives here and nowhere else:
  - M365  → Path A: app-only client-credentials token (shared, cached, from .env)
  - Slack → Path B: per-user OAuth user token (from the credentials table)
  - Jira  → service account basic auth (from .env)
If the path ever changes, the pulls do not."""
from __future__ import annotations

import time

import requests

from . import config, store

_m365_cache: dict = {"token": None, "exp": 0.0}


def m365_token() -> str:
    """App-only Graph token (AUTH.md Path A). Cached until near expiry."""
    if _m365_cache["token"] and time.time() < _m365_cache["exp"] - 120:
        return _m365_cache["token"]
    tenant = config.env("M365_TENANT_ID")
    r = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": config.env("M365_CLIENT_ID"),
            "client_secret": config.env("M365_CLIENT_SECRET"),
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    r.raise_for_status()
    tok = r.json()
    _m365_cache.update(token=tok["access_token"], exp=time.time() + int(tok.get("expires_in", 3600)))
    return _m365_cache["token"]


class MissingConsent(Exception):
    """User has not completed Slack OAuth yet — surfaced as an onboarding step,
    never swallowed."""


def slack_user_token(user_email: str) -> str:
    cred = store.get_credential("slack", user_email)
    if not cred:
        raise MissingConsent(
            f"No Slack user token for {user_email}. Send them the consent link (AUTH.md)."
        )
    return cred["access_token"]


def slack_bot_token() -> str:
    return config.env("SLACK_BOT_TOKEN")


def slack_exchange_code(code: str) -> dict:
    """OAuth redirect handler calls this: exchange the code, store the USER
    token keyed to the roster email that owns that Slack ID."""
    r = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": config.env("SLACK_CLIENT_ID"),
            "client_secret": config.env("SLACK_CLIENT_SECRET"),
            "code": code,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack OAuth exchange failed: {data.get('error')}")
    authed = data.get("authed_user") or {}
    slack_id, user_token = authed.get("id"), authed.get("access_token")
    if not user_token:
        raise RuntimeError("Slack OAuth response carried no user token — check user_scope in the consent URL")
    email = next((p["email"] for p in config.people() if p.get("slack_user_id") == slack_id), None)
    if not email:
        raise RuntimeError(f"Slack user {slack_id} not in roster — add them before consent")
    store.save_credential("slack", email, user_token, scopes=authed.get("scope", ""))
    return {"email": email, "slack_id": slack_id}


def jira_auth() -> tuple[str, str]:
    return (config.env("JIRA_EMAIL"), config.env("JIRA_API_TOKEN"))


def jira_base() -> str:
    return config.env("JIRA_BASE_URL").rstrip("/")
