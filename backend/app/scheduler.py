"""APScheduler daily job — weekdays after ASX close, Australia/Sydney."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import market_tz, settings

logger = logging.getLogger(__name__)


def _run_scheduled_pipeline() -> None:
    from .services.pipeline import run_daily_pipeline

    run_daily_pipeline(trigger="scheduled")


def start_scheduler() -> BackgroundScheduler:
    tz = market_tz()
    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(
        _run_scheduled_pipeline,
        CronTrigger(
            day_of_week="mon-fri",
            hour=settings.schedule_hour,
            minute=settings.schedule_minute,
            timezone=tz,
        ),
        id="daily_pipeline",
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info(
        "scheduler started: mon-fri %02d:%02d %s",
        settings.schedule_hour,
        settings.schedule_minute,
        settings.timezone,
    )
    return scheduler
