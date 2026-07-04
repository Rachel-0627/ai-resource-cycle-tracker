from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...models import Stock
from ...schemas import Message, StockCreate, StockUpdate, StockWithScore
from ...services.watchlist import build_stock_view
from ..deps import get_db

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _get_stock_or_404(db: Session, code: str) -> Stock:
    stock = db.query(Stock).filter_by(code=code.upper()).one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"stock {code.upper()} not found")
    return stock


@router.get("", response_model=list[StockWithScore])
def list_stocks(active: bool | None = True, db: Session = Depends(get_db)):
    q = db.query(Stock)
    if active is not None:
        q = q.filter_by(active=active)
    stocks = q.order_by(Stock.code).all()
    views = [build_stock_view(db, s) for s in stocks]
    views.sort(key=lambda v: v.latest_score.cycle_score if v.latest_score else -1, reverse=True)
    return views


@router.post("", response_model=StockWithScore, status_code=201)
def create_stock(payload: StockCreate, db: Session = Depends(get_db)):
    code = payload.code.strip().upper()
    existing = db.query(Stock).filter_by(code=code).one_or_none()
    if existing is not None:
        if not existing.active:  # re-activate a soft-deleted stock
            existing.active = True
            existing.name = payload.name
            existing.commodity = payload.commodity
            existing.stage = payload.stage
            db.commit()
            return build_stock_view(db, existing)
        raise HTTPException(status_code=409, detail=f"stock {code} already exists")
    stock = Stock(
        code=code,
        name=payload.name.strip(),
        commodity=payload.commodity.strip(),
        stage=payload.stage.strip(),
        notes=payload.notes.strip(),
    )
    db.add(stock)
    db.commit()
    return build_stock_view(db, stock)


@router.get("/{code}", response_model=StockWithScore)
def get_stock(code: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    return build_stock_view(db, stock, include_components=True)


@router.put("/{code}", response_model=StockWithScore)
def update_stock(code: str, payload: StockUpdate, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    for field in ("name", "commodity", "stage", "notes", "active"):
        value = getattr(payload, field)
        if value is not None:
            setattr(stock, field, value)
    if payload.resource_score_override is not None:
        stock.resource_score_override = payload.resource_score_override
    if payload.risk_score_override is not None:
        stock.risk_score_override = payload.risk_score_override
    if payload.clear_resource_override:
        stock.resource_score_override = None
    if payload.clear_risk_override:
        stock.risk_score_override = None
    db.commit()
    return build_stock_view(db, stock, include_components=True)


@router.delete("/{code}", response_model=Message)
def deactivate_stock(code: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    stock.active = False
    db.commit()
    return Message(detail=f"stock {stock.code} deactivated")
