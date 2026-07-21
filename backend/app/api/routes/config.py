from typing import Any
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...schemas import ConfigHistoryOut
from ...services.config_service import DEFAULTS, get_all_config, list_config_history, set_config
from ..deps import get_db
from ..security import require_admin_access

router = APIRouter(prefix="/config", tags=["config"], dependencies=[Depends(require_admin_access)])


@router.get("")
def read_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_all_config(db)


@router.get("/history", response_model=list[ConfigHistoryOut])
def read_config_history(limit: int = 50, db: Session = Depends(get_db)):
    rows = list_config_history(db, limit=limit)
    return [
        ConfigHistoryOut(
            id=row.id,
            key=row.key,
            old_value=json.loads(row.old_value) if row.old_value is not None else None,
            new_value=json.loads(row.new_value),
            changed_by=row.changed_by,
            source=row.source,
            changed_at=row.changed_at,
        )
        for row in rows
    ]


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
        if key == "commodity_instruments":
            if set(value) != set(DEFAULTS["commodity_instruments"]):
                raise HTTPException(status_code=422, detail="commodity_instruments must define every commodity")
            if any(not str(instrument).strip() for instrument in value.values()):
                raise HTTPException(status_code=422, detail="commodity instrument values must be non-empty")
        if key == "benchmark_instrument":
            if not str(value).strip():
                raise HTTPException(status_code=422, detail="benchmark_instrument must be non-empty")
    for key, value in payload.items():
        set_config(db, key, value, changed_by="settings_page", source="api:/config")
    return get_all_config(db)
