from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


class SourceBlockedError(Exception):
    """The announcement source appears to be blocking us (bot protection).

    The pipeline catches this, keeps using stored announcements, and flags the
    degradation in run stats and the daily report — it must not crash the run.
    """


@dataclass
class RawAnnouncement:
    ann_id: str
    headline: str
    ann_date: datetime  # timezone-aware
    url: str
    price_sensitive: bool
    raw: dict = field(default_factory=dict)  # original payload item, persisted for traceability


class AnnouncementSource(ABC):
    @abstractmethod
    def fetch(self, code: str, count: int = 20) -> list[RawAnnouncement]:
        """Fetch the most recent announcements for an ASX code."""


def get_announcement_source(name: str) -> AnnouncementSource:
    if name == "asx_json":
        from .asx_announcements import AsxJsonAnnouncementSource

        return AsxJsonAnnouncementSource()
    raise ValueError(f"unknown announcement source: {name}")
