"""Optional SMTP email notifier for daily reports."""

from email.message import EmailMessage
import logging
import smtplib

from ..config import settings
from .base import Notifier, PushResult

logger = logging.getLogger(__name__)


class EmailNotifier(Notifier):
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        use_tls: bool | None = None,
    ):
        self.host = host if host is not None else settings.email_smtp_host
        self.port = port if port is not None else settings.email_smtp_port
        self.username = username if username is not None else settings.email_smtp_username
        self.password = password if password is not None else settings.email_smtp_password
        self.sender = sender if sender is not None else settings.email_from
        self.recipient = recipient if recipient is not None else settings.email_to
        self.use_tls = use_tls if use_tls is not None else settings.email_use_tls

    def send(self, text: str) -> PushResult:
        if not self.host or not self.sender or not self.recipient:
            logger.info("email not configured — skipping push (report still persisted)")
            return PushResult(sent=False, skipped=True)

        message = EmailMessage()
        message["Subject"] = "AI Resource Cycle Tracker Daily Report"
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(text)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(message)
        except Exception as exc:
            logger.warning("email push failed: %s", exc)
            return PushResult(sent=False, error=str(exc))
        return PushResult(sent=True)
