"""AI analysis layer interface — MVP-1 ships the no-op implementation only.

Phase-2 plugs in a ClaudeAnalyzer (announcement summary + structured metric
extraction + confidence) by implementing AnnouncementAnalyzer and switching
settings.ai_analyzer. The pipeline already calls the analyzer after rule
classification and persists non-None results to announcements.ai_summary /
ai_metrics — no pipeline changes will be needed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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


def get_analyzer(name: str) -> AnnouncementAnalyzer:
    if name == "noop":
        return NoopAnalyzer()
    raise ValueError(f"unknown ai analyzer: {name}")
