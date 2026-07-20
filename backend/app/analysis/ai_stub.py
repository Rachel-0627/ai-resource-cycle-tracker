"""AI analysis layer interface — MVP-1 ships the no-op implementation only.

Phase-2 plugs in a ClaudeAnalyzer (announcement summary + structured metric
extraction + confidence) by implementing AnnouncementAnalyzer and switching
settings.ai_analyzer. The pipeline already calls the analyzer after rule
classification and persists non-None results to announcements.ai_summary /
ai_metrics — no pipeline changes will be needed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)


@dataclass
class AnnouncementInsight:
    summary: str
    metrics: dict = field(default_factory=dict)  # e.g. grade/width/depth extractions
    confidence: float = 0.0


class AnnouncementAnalyzer(ABC):
    @abstractmethod
    def analyze(self, headline: str, ann_type: str) -> AnnouncementInsight | None:
        """Return None when there is nothing to add (rules-only mode)."""


class NoopAnalyzer(AnnouncementAnalyzer):
    def analyze(self, headline: str, ann_type: str) -> AnnouncementInsight | None:
        return None


class PaidCallsDisabledAnalyzer(AnnouncementAnalyzer):
    """Cost-safe placeholder when a paid analyzer is selected but not enabled."""

    def __init__(self, reason: str):
        self.reason = reason

    def analyze(self, headline: str, ann_type: str) -> AnnouncementInsight | None:
        logger.info("AI analyzer skipped: %s", self.reason)
        return None


class ClaudeAnalyzer(AnnouncementAnalyzer):
    """Anthropic Messages API analyzer for announcement headlines."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 400,
        timeout: float = 20.0,
        post: Callable[..., httpx.Response] | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._post = post or httpx.post

    def analyze(self, headline: str, ann_type: str) -> AnnouncementInsight | None:
        if not headline.strip():
            return None

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "system": (
                "You analyze ASX resource-company announcement headlines for a "
                "research dashboard. Return only compact JSON. Do not provide "
                "investment advice or buy/sell recommendations."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Analyze this announcement headline.\n"
                        f"Rule classification: {ann_type}\n"
                        f"Headline: {headline}\n\n"
                        "Return JSON with keys: summary, metrics, confidence.\n"
                        "summary: one neutral sentence, max 180 characters.\n"
                        "metrics: object containing any explicitly stated grade, width, "
                        "depth, project, commodity, stage, or deal terms. Use null or omit "
                        "unknown values. Do not infer unstated facts.\n"
                        "confidence: number from 0 to 1 for extraction confidence."
                    ),
                }
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            response = self._post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = self._content_text(data)
            parsed = self._parse_json_object(text)
        except Exception as exc:
            logger.warning("Claude announcement analysis failed: %s", exc)
            return None

        summary = str(parsed.get("summary") or "").strip()
        if not summary:
            return None
        metrics = parsed.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        confidence = self._bounded_float(parsed.get("confidence"), default=0.0)
        metrics = {
            **metrics,
            "confidence": confidence,
            "provider": "anthropic",
            "model": self.model,
        }
        return AnnouncementInsight(summary=summary[:240], metrics=metrics, confidence=confidence)

    @staticmethod
    def _content_text(data: dict[str, Any]) -> str:
        parts = data.get("content") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        return "\n".join(texts).strip()

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return {}
            value = json.loads(text[start : end + 1])
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _bounded_float(value: Any, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, numeric))


def get_analyzer(name: str) -> AnnouncementAnalyzer:
    if name == "noop":
        return NoopAnalyzer()
    if name == "claude":
        from ..config import settings

        if not settings.ai_analyzer_allow_paid_calls:
            return PaidCallsDisabledAnalyzer("AI_ANALYZER_ALLOW_PAID_CALLS is false")
        if not settings.anthropic_api_key:
            return PaidCallsDisabledAnalyzer("ANTHROPIC_API_KEY is empty")
        return ClaudeAnalyzer(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
    raise ValueError(f"unknown ai analyzer: {name}")
