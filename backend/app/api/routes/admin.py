import json

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from ...database import SessionLocal
from ...models import PipelineRun
from ...notify.telegram import TelegramNotifier
from ...schemas import Message, PipelineRunOut
from ..deps import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


def _pipeline_task() -> None:
    from ...services.pipeline import run_daily_pipeline

    run_daily_pipeline(trigger="manual")


def _replay_task(days: int) -> None:
    from ...services.replay import run_replay

    with SessionLocal() as session:
        run_replay(session, days=days)


@router.post("/run-pipeline", response_model=Message)
def run_pipeline(background: BackgroundTasks):
    background.add_task(_pipeline_task)
    return Message(detail="pipeline started in background; poll /api/admin/runs")


@router.post("/run-replay", response_model=Message)
def run_replay_endpoint(background: BackgroundTasks, days: int = 400):
    background.add_task(_replay_task, days)
    return Message(detail=f"replay ({days} bars) started in background")


@router.get("/runs", response_model=list[PipelineRunOut])
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    runs = db.query(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit).all()
    return [
        PipelineRunOut(
            id=r.id,
            run_at=r.run_at,
            trigger=r.trigger,
            status=r.status,
            stats=json.loads(r.stats_json or "{}"),
            finished_at=r.finished_at,
        )
        for r in runs
    ]


@router.post("/test-telegram", response_model=Message)
def test_telegram():
    result = TelegramNotifier().send(
        "<b>AI Resource Cycle Tracker</b>\nTelegram channel is configured correctly."
    )
    if result.skipped:
        return Message(detail="telegram not configured (set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
    if not result.sent:
        return Message(detail=f"telegram push failed: {result.error}")
    return Message(detail="test message sent")
