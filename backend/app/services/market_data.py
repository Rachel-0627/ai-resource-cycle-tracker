"""Sync yfinance daily bars into price_bars / commodity_bars (incremental, idempotent)."""

import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..datasources.commodity import fetch_commodity_daily
from ..datasources.yfinance_ohlcv import fetch_daily
from ..models import CommodityBar, PriceBar, Stock
from .config_service import get_config

logger = logging.getLogger(__name__)


def sync_stock_prices(session: Session, stock: Stock) -> int:
    """Fetch new daily bars for a stock. First run backfills ~2y (≈500 trading days)."""
    last: date | None = (
        session.query(func.max(PriceBar.date)).filter(PriceBar.stock_id == stock.id).scalar()
    )
    if last is not None:
        df = fetch_daily(f"{stock.code}.AX", start=last + timedelta(days=1))
    else:
        df = fetch_daily(f"{stock.code}.AX", period="2y")
    if df.empty:
        return 0

    existing = {
        d
        for (d,) in session.query(PriceBar.date)
        .filter(PriceBar.stock_id == stock.id, PriceBar.date >= df["date"].min())
        .all()
    }
    added = 0
    for row in df.itertuples(index=False):
        if row.date in existing:
            continue
        session.add(
            PriceBar(
                stock_id=stock.id,
                date=row.date,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=int(row.volume),
            )
        )
        added += 1
    session.commit()
    return added


def sync_instrument(session: Session, instrument: str) -> int:
    last: date | None = (
        session.query(func.max(CommodityBar.date))
        .filter(CommodityBar.instrument == instrument)
        .scalar()
    )
    df = fetch_commodity_daily(instrument, start=last + timedelta(days=1) if last else None)
    if df.empty:
        return 0
    existing = {
        d
        for (d,) in session.query(CommodityBar.date)
        .filter(CommodityBar.instrument == instrument, CommodityBar.date >= df["date"].min())
        .all()
    }
    added = 0
    for row in df.itertuples(index=False):
        if row.date in existing:
            continue
        session.add(CommodityBar(instrument=instrument, date=row.date, close=float(row.close)))
        added += 1
    session.commit()
    return added


def sync_all_instruments(session: Session) -> dict[str, int]:
    """Commodity proxies + backtest benchmark."""
    instruments = set(get_config(session, "commodity_instruments").values())
    instruments.add(get_config(session, "benchmark_instrument"))
    results: dict[str, int] = {}
    for instrument in sorted(instruments):
        try:
            results[instrument] = sync_instrument(session, instrument)
        except Exception as exc:
            logger.warning("commodity sync failed for %s: %s", instrument, exc)
            results[instrument] = -1
    return results
