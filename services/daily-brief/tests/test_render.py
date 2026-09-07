from datetime import date, datetime, timedelta, timezone

from brief import render, score
from tests.conftest import make_item

MONDAY = date(2026, 7, 27)


def _sel():
    items = [
        make_item(id="i1", ask_summary="Northwind MSA signature routing", repeat_count=2,
                  first_seen=datetime(2026, 7, 23, tzinfo=timezone.utc), days_open=4,
                  counterparty="Legal Lead <legal@acme.example.com>"),
        make_item(id="i2", block="B", source="slack", source_id="C1:1.1",
                  ask_summary="Share the Product Roadmap Confluence page", is_blocking=True,
                  first_seen=datetime(2026, 7, 21, tzinfo=timezone.utc), days_open=6,
                  counterparty="Product Lead"),
        make_item(id="i3", block="C", source="jira", source_id="PROJ-101",
                  ask_summary="PROJ-101 awaiting your acceptance criteria", stale_flag=True,
                  first_seen=datetime(2026, 7, 18, tzinfo=timezone.utc), days_open=9,
                  permalink="https://acme.atlassian.net/browse/PROJ-101"),
        make_item(id="i4", ask_summary="Contoso Capital intro call scheduling",
                  counterparty_class="lender",
                  first_seen=datetime(2026, 7, 23, tzinfo=timezone.utc), days_open=4),
        make_item(id="i5", ask_summary="Fabrikam deck final review", deadline=MONDAY,
                  first_seen=datetime(2026, 7, 26, tzinfo=timezone.utc), days_open=1),
        make_item(id="i6", ask_summary="Tailspin billing dispute response",
                  first_seen=datetime(2026, 7, 26, tzinfo=timezone.utc), days_open=1),
    ]
    d = [make_item(id="d1", block="D", ask_summary="Litware lender portal pricing",
                   counterparty="Litware Account Manager", days_open=6,
                   first_seen=datetime(2026, 7, 21, tzinfo=timezone.utc))]
    return score.select(items + d, MONDAY)


def test_subject_line_format():
    sel = _sel()
    subject, _, _ = render.render(sel, MONDAY)
    assert subject.startswith("Your open loops, Monday July 27 - ")
    assert "blocking" in subject and "overdue" in subject


def test_day_counters_and_links():
    _, html, _ = render.render(_sel(), MONDAY)
    assert "open 4 days" in html
    assert "open 9 days" in html
    assert "due today" in html
    assert "https://acme.atlassian.net/browse/PROJ-101" in html
    assert "Jira · open PROJ-101" in html


def test_numbering_is_continuous_and_frozen():
    sel = _sel()
    _, html, ordered = render.render(sel, MONDAY)
    # every shown A–C item then every D item, numbered 1..N with no repeats
    assert len(ordered) == len(sel["shown"]) + len(sel["waiting"])
    assert len(set(ordered)) == len(ordered)
    assert f"{len(ordered)}. " in html or f"{len(ordered)}." in html


def test_footer_and_no_images():
    _, html, _ = render.render(_sel(), MONDAY)
    assert "close 4, 7" in html          # reply-to-close instruction
    assert "<img" not in html            # spec: no images
    assert "http://" not in html.replace("http://brief", "")  # no insecure asset refs


def test_empty_state():
    sel = score.select([], MONDAY)
    subject, html, ordered = render.render(sel, MONDAY)
    assert subject == "Your open loops, Monday July 27 - all clear"
    assert "No open loops detected" in html
    assert ordered == []
