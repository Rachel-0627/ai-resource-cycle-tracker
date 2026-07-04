import logging

import httpx

from ..config import settings
from .base import Notifier, PushResult

logger = logging.getLogger(__name__)

MAX_CHUNK = 4000  # Telegram hard limit is 4096


def _split_chunks(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_CHUNK:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


class TelegramNotifier(Notifier):
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token if token is not None else settings.telegram_bot_token
        self.chat_id = chat_id if chat_id is not None else settings.telegram_chat_id

    def send(self, text: str) -> PushResult:
        if not self.token or not self.chat_id:
            logger.info("telegram not configured — skipping push (report still persisted)")
            return PushResult(sent=False, skipped=True)
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            for chunk in _split_chunks(text):
                resp = httpx.post(
                    url,
                    json={
                        "chat_id": self.chat_id,
                        "text": chunk,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=20,
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("telegram push failed: %s", exc)
            return PushResult(sent=False, error=str(exc))
        return PushResult(sent=True)
