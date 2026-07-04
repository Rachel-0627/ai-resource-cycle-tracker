from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from ...models import Signal, Stock
from ...schemas import SignalOut
from ..deps import get_db
from ..serializers import signal_out

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalOut])
def list_signals(
    date_from: date | None = None,
    date_to: date | None = None,
    signal_type: str | None = None,
    label: str | None = None,
    code: str | None = None,
    source: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    q = (
        db.query(Signal, Stock)
        .join(Stock, Signal.stock_id == Stock.id)
        .options(joinedload(Signal.returns))
    )
    if date_from:
        q = q.filter(Signal.date >= date_from)
    if date_to:
        q = q.filter(Signal.date <= date_to)
    if signal_type:
        q = q.filter(Signal.signal_type == signal_type)
    if label:
        q = q.filter(Signal.label == label)
    if code:
        q = q.filter(Stock.code == code.upper())
    if source:
        q = q.filter(Signal.source == source)
    rows = q.order_by(Signal.date.desc(), Stock.code).limit(min(limit, 1000)).all()
    return [signal_out(sig, stock) for sig, stock in rows]
