from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # repo root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: str = str(BASE_DIR / "data" / "tracker.db")
    timezone: str = "Australia/Sydney"

    # data sources — the markitdigital gateway is what asx.com.au itself uses;
    # the access token below is the public one embedded in the ASX website.
    asx_api_base: str = "https://asx.api.markitdigital.com/asx-research/1.0"
    asx_access_token: str = "83ff96335c2d45a094df02a206a39ff4"
    announcement_source: str = "asx_json"
    announcement_fetch_count: int = 20
    request_delay_min: float = 1.5
    request_delay_max: float = 3.0
    request_max_retries: int = 3
    ohlcv_backfill_days: int = 500

    # scheduler (Australia/Sydney, after ASX 16:00 close)
    enable_scheduler: bool = False
    schedule_hour: int = 18
    schedule_minute: int = 30

    # notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # AI analysis layer (MVP-1: rules only; phase-2 may set "claude")
    ai_analyzer: str = "noop"


settings = Settings()


def market_tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)
