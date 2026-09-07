import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql:///brief_test")


def make_item(**over) -> dict:
    base = {
        "id": "abc123",
        "user_email": "sponsor@acme.example.com",
        "block": "A",
        "source": "email",
        "source_id": "conv-1",
        "permalink": "https://outlook.office.com/x",
        "ask_summary": "Northwind MSA signature routing",
        "counterparty": "Legal Lead <legal@acme.example.com>",
        "counterparty_class": "internal",
        "is_blocking": False,
        "deadline": None,
        "confidence": 0.9,
        "repeat_count": 1,
        "stale_flag": False,
        "tier": None,
        "score": None,
        "first_seen": datetime.now(timezone.utc) - timedelta(days=2),
        "last_ask_at": datetime.now(timezone.utc) - timedelta(days=2),
        "days_open": 2,
        "closed_at": None,
    }
    base.update(over)
    return base


@pytest.fixture
def pg():
    """Fresh schema in the brief_test database for store-level tests."""
    import psycopg

    from db.migrate import migrate

    url = os.environ["DATABASE_URL"]
    with psycopg.connect("postgresql:///postgres", autocommit=True) as c:
        c.execute("drop database if exists brief_test")
        c.execute("create database brief_test")
    migrate(url)
    from brief import store
    store.sync_roster([
        {"email": "sponsor@acme.example.com", "key": "sponsor", "full_name": "Sponsor Example",
         "slack_user_id": "U_EXAMPLE_SPONSOR", "jira_account_id": None,
         "mail_platform": "m365", "timezone": "America/Chicago", "active": True},
    ])
    return url
