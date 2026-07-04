from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PushResult:
    sent: bool
    skipped: bool = False  # not configured — a valid state, not an error
    error: str | None = None


class Notifier(ABC):
    @abstractmethod
    def send(self, text: str) -> PushResult:
        """Send a report. Implementations must degrade gracefully when
        unconfigured (skip, don't raise) — reports are persisted regardless."""
