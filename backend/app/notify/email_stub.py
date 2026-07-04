"""Email channel — interface reserved for a later phase (SMTP config needed)."""

import logging

from .base import Notifier, PushResult

logger = logging.getLogger(__name__)


class EmailNotifier(Notifier):
    def send(self, text: str) -> PushResult:
        logger.info("email notifier is a stub in MVP-1 — skipping")
        return PushResult(sent=False, skipped=True)
