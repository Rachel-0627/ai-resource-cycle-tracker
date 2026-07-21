import json
from datetime import datetime, timezone

import httpx

from app.analysis.ai_stub import (
    AnnouncementDocumentFetcher,
    ClaudeAnalyzer,
    NoopAnalyzer,
    PaidCallsDisabledAnalyzer,
    RuleBasedFullTextAnalyzer,
    get_analyzer,
)
from app.config import settings
from app.datasources.base import AnnouncementSource, RawAnnouncement
from app.models import Announcement, Stock
from app.services.announcements import sync_announcements


def test_default_analyzer_is_noop():
    assert isinstance(get_analyzer("noop"), NoopAnalyzer)
    assert get_analyzer("noop").analyze("High-Grade Drill Results", "DRILL_RESULTS") is None


def test_rules_fulltext_analyzer_extracts_intercepts_project_and_depth():
    analyzer = get_analyzer("rules_fulltext")
    assert isinstance(analyzer, RuleBasedFullTextAnalyzer)
    assert analyzer.requires_document_text is True

    body = (
        "Drilling at the Bankan Project returned 12.5m at 4.2 g/t Au from 88m. "
        "Additional lithium zone returned 30m at 1.1% Li2O from 40m."
    )
    insight = analyzer.analyze(
        "High-Grade Drill Results Extend Mineralisation",
        "DRILL_RESULTS",
        body_text=body,
        source_url="https://example.com/ann.pdf",
    )

    assert insight is not None
    assert "12.5m at 4.2g/t gold from 88m" in insight.summary
    assert insight.metrics["project"] == "Bankan"
    assert insight.metrics["commodities"] == ["gold", "lithium"]
    first = insight.metrics["intercepts"][0]
    assert first["width_m"] == 12.5
    assert first["grade"] == 4.2
    assert first["unit"].lower() == "g/t"
    assert first["commodity"] == "gold"
    assert first["depth_m"] == 88.0
    assert insight.metrics["provider"] == "rules"
    assert insight.metrics["document_chars"] == len(body)


def test_document_fetcher_extracts_and_bounds_plain_text():
    def fake_get(url, timeout, follow_redirects):
        return httpx.Response(
            200,
            content=b"Line one\n\n  12m at 3.4 g/t Au from 50m  ",
            headers={"content-type": "text/plain"},
            request=httpx.Request("GET", url),
        )

    fetcher = AnnouncementDocumentFetcher(get=fake_get, max_chars=24)
    doc = fetcher.fetch("https://example.com/a.txt")

    assert doc is not None
    assert doc.status == "ok"
    assert doc.text == "Line one 12m at 3.4 g/t "


def test_document_fetcher_cleans_html_body_fallback():
    html = b"""
    <!doctype html>
    <html>
      <head>
        <title>Announcement</title>
        <style>.hidden { display: none; }</style>
        <script>window.noise = "99m at 99 g/t Au";</script>
      </head>
      <body>
        <header>Site header Subscribe</header>
        <nav>Home Markets Announcements</nav>
        <div class="cookie banner">Accept cookies</div>
        <main>
          <article>
            <h1>High-Grade Drill Results</h1>
            <p>Drilling at the Bankan Project returned <strong>12m at 3.4 g/t Au</strong> from 50m.</p>
            <p>Metallurgical work remains ongoing &amp; further assays are pending.</p>
          </article>
        </main>
        <footer>Terms Privacy Contact</footer>
      </body>
    </html>
    """

    def fake_get(url, timeout, follow_redirects):
        return httpx.Response(
            200,
            content=html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", url),
        )

    fetcher = AnnouncementDocumentFetcher(get=fake_get)
    doc = fetcher.fetch("https://example.com/ann.html")

    assert doc is not None
    assert doc.status == "ok"
    assert "High-Grade Drill Results" in doc.text
    assert "12m at 3.4 g/t Au from 50m" in doc.text
    assert "Metallurgical work remains ongoing & further assays are pending." in doc.text
    assert "window.noise" not in doc.text
    assert "Home Markets" not in doc.text
    assert "Accept cookies" not in doc.text
    assert "Terms Privacy" not in doc.text

    insight = RuleBasedFullTextAnalyzer().analyze(
        "High-Grade Drill Results",
        "DRILL_RESULTS",
        body_text=doc.text,
    )
    assert insight is not None
    assert insight.metrics["intercepts"][0]["width_m"] == 12.0
    assert insight.metrics["intercepts"][0]["grade"] == 3.4
    assert insight.metrics["intercepts"][0]["depth_m"] == 50.0


def test_claude_analyzer_is_cost_gated(monkeypatch):
    monkeypatch.setattr(settings, "ai_analyzer_allow_paid_calls", False)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    analyzer = get_analyzer("claude")
    assert isinstance(analyzer, PaidCallsDisabledAnalyzer)
    assert analyzer.analyze("High-Grade Drill Results", "DRILL_RESULTS") is None


def test_claude_analyzer_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ai_analyzer_allow_paid_calls", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    analyzer = get_analyzer("claude")
    assert isinstance(analyzer, PaidCallsDisabledAnalyzer)


def test_claude_analyzer_parses_response():
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        content = {
            "summary": "Headline reports high-grade gold drill results.",
            "metrics": {"commodity": "gold", "stage": "drill_results"},
            "confidence": 0.82,
        }
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": json_dumps(content)}]},
            request=httpx.Request("POST", url),
        )

    analyzer = ClaudeAnalyzer(
        api_key="test-key",
        model="claude-test",
        max_tokens=123,
        post=fake_post,
    )
    insight = analyzer.analyze(
        "High-Grade Gold Drill Results",
        "DRILL_RESULTS",
        body_text="Best intercept was 8m at 6.1 g/t Au from 120m.",
        source_url="https://example.com/ann.pdf",
    )

    assert insight is not None
    assert insight.summary == "Headline reports high-grade gold drill results."
    assert insight.confidence == 0.82
    assert insight.metrics["commodity"] == "gold"
    assert insight.metrics["provider"] == "anthropic"
    assert insight.metrics["model"] == "claude-test"
    assert calls[0]["headers"]["x-api-key"] == "test-key"
    assert calls[0]["json"]["max_tokens"] == 123
    prompt = calls[0]["json"]["messages"][0]["content"]
    assert "Document URL: https://example.com/ann.pdf" in prompt
    assert "8m at 6.1 g/t Au" in prompt


def test_claude_analyzer_returns_none_on_bad_response():
    def fake_post(url, headers, json, timeout):
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "not json"}]},
            request=httpx.Request("POST", url),
        )

    analyzer = ClaudeAnalyzer(api_key="test-key", model="claude-test", post=fake_post)
    assert analyzer.analyze("High-Grade Gold Drill Results", "DRILL_RESULTS") is None


def test_sync_announcements_fetches_document_for_fulltext_analyzer(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    class FakeSource(AnnouncementSource):
        def fetch(self, code: str, count: int = 20) -> list[RawAnnouncement]:
            return [
                RawAnnouncement(
                    ann_id="ann-1",
                    headline="High-Grade Drill Results",
                    ann_date=datetime(2026, 7, 20, tzinfo=timezone.utc),
                    url="https://example.com/ann.pdf",
                    price_sensitive=True,
                    raw={"id": "ann-1"},
                )
            ]

    class FakeFetcher:
        def fetch(self, url: str):
            from app.analysis.ai_stub import AnnouncementDocument

            return AnnouncementDocument(
                url=url,
                text="Results at the Bankan Project include 9m at 5.5 g/t Au from 101m.",
                content_type="application/pdf",
            )

    result = sync_announcements(
        db_session,
        stock,
        FakeSource(),
        RuleBasedFullTextAnalyzer(),
        document_fetcher=FakeFetcher(),
    )

    assert result == {"new": 1}
    ann = db_session.query(Announcement).one()
    assert ann.ai_summary == "Reports 9m at 5.5g/t gold from 101m."
    metrics = json.loads(ann.ai_metrics)
    assert metrics["intercepts"][0]["width_m"] == 9.0
    assert metrics["intercepts"][0]["depth_m"] == 101.0
    assert metrics["document"]["status"] == "ok"
    assert metrics["document"]["text"] == ""


def json_dumps(value):
    return json.dumps(value)
