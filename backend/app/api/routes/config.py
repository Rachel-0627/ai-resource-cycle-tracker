from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...services.config_service import DEFAULTS, get_all_config, set_config
from ..deps import get_db

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
def read_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_all_config(db)


@router.put("")
def update_config(payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    for key, value in payload.items():
        if key not in DEFAULTS:
            raise HTTPException(status_code=422, detail=f"unknown config key: {key}")
        if key == "weights":
            if set(value) != set(DEFAULTS["weights"]):
                raise HTTPException(status_code=422, detail="weights must define exactly the 5 sub-scores")
            total = sum(float(v) for v in value.values())
            if abs(total - 1.0) > 0.001:
                raise HTTPException(status_code=422, detail=f"weights must sum to 1.0 (got {total:.3f})")
        if key == "label_thresholds":
            try:
                high, watch, monitor = (
                    float(value["high_priority"]), float(value["watch_closely"]), float(value["monitor"])
                )
            except (KeyError, TypeError, ValueError):
                raise HTTPException(status_code=422, detail="label_thresholds needs high_priority/watch_closely/monitor")
            if not (high > watch > monitor > 0):
                raise HTTPException(status_code=422, detail="thresholds must satisfy high > watch > monitor > 0")
    for key, value in payload.items():
        set_config(db, key, value)
    return get_all_config(db)
