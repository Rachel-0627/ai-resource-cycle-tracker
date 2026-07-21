from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...schemas import BacktestSummary, WeightCalibrationOut
from ...services.backtest import backtest_summary
from ...services.weight_calibration import calibrate_weights
from ..deps import get_db

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/summary", response_model=BacktestSummary)
def summary(group_by: str = "signal_type", source: str = "all", db: Session = Depends(get_db)):
    if source not in ("all", "live", "replay"):
        raise HTTPException(status_code=422, detail="source must be all/live/replay")
    try:
        return backtest_summary(db, group_by=group_by, source=source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/weight-calibration", response_model=WeightCalibrationOut)
def weight_calibration(
    horizon_days: int = 20,
    target: str = "excess",
    db: Session = Depends(get_db),
):
    try:
        return calibrate_weights(db, horizon_days=horizon_days, target=target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
