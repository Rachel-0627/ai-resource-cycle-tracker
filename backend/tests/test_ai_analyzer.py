import json

import httpx

from app.analysis.ai_stub import ClaudeAnalyzer, NoopAnalyzer, PaidCallsDisabledAnalyzer, get_analyzer
from app.config import settings


def test_default_analyzer_is_noop():
    assert isinstance(get_analyzer("noop"), NoopAnalyzer)
    assert get_analyzer("noop").analyze("High-Grade Drill Results", "DRILL_RESULTS") is None


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
    insight = analyzer.analyze("High-Grade Gold Drill Results", "DRILL_RESULTS")

    assert insight is not None
    assert insight.summary == "Headline reports high-grade gold drill results."
    assert insight.confidence == 0.82
    assert insight.metrics["commodity"] == "gold"
    assert insight.metrics["provider"] == "anthropic"
    assert insight.metrics["model"] == "claude-test"
    assert calls[0]["headers"]["x-api-key"] == "test-key"
    assert calls[0]["json"]["max_tokens"] == 123


def test_claude_analyzer_returns_none_on_bad_response():
    def fake_post(url, headers, json, timeout):
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "not json"}]},
            request=httpx.Request("POST", url),
        )

    analyzer = ClaudeAnalyzer(api_key="test-key", model="claude-test", post=fake_post)
    assert analyzer.analyze("High-Grade Gold Drill Results", "DRILL_RESULTS") is None


def json_dumps(value):
    return json.dumps(value)
