"""Historical replay of PRICE-BASED signals over backfilled bars.

Purpose: forward-only collection would leave the backtest page empty for
months; the PRD's goal is validating signals against history. Replay runs the
exact same indicator/signal pure functions bar-by-bar, so live and replayed
triggers cannot diverge.

Honesty constraints:
- Only REL_VOL_SPIKE / BREAKOUT_60D / BREAKOUT_252D are replayed. Announcement
  history is capped (~20 most recent per stock), so KEY_ANNOUNCEMENT and any
  historical Cycle Score cannot be reconstructed — replay signals carry
  source='replay' with label/cycle_score NULL and are excluded from
  label/score-bucket statistics.
- Early bars lack the 252d window; those days simply cannot fire BREAKOUT_252D,
  same as live.
"""

import logging
from sqlalchemy.orm import Session

from ..analysis.indicators import DailyBar, compute_indicators
from ..analysis.signals import detect_price_signals
from ..models import PriceBar, Stock
from .backtest import fill_pending_returns
from .config_service import get_config
from .signal_service import persist_signals

logger = logging.getLogger(__name__)

MIN_HISTORY = 21  # rel_vol needs 20 prior bars


def replay_stock(session: Session, stock: Stock, days: int, thresholds: dict) -> int:
    rows = (
        session.query(PriceBar)
        .filter(PriceBar.stock_id == stock.id)
        .order_by(PriceBar.date)
        .all()
    )
    bars = [
        DailyBar(date=r.date, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for r in rows
    ]
    if len(bars) <= MIN_HISTORY:
        return 0
    start_idx = max(MIN_HISTORY, len(bars) - days)
    added = 0
    for i in range(start_idx, len(bars)):
        ind = compute_indicators(bars[: i + 1])
        candidates = detect_price_signals(ind, thresholds)
        if candidates:
            added += persist_signals(
                session,
                stock,
                bars[i].date,
                candidates,
                price_at_signal=bars[i].close,
                source="replay",
            )
    return added


def run_replay(session: Session, days: int = 400, codes: list[str] | None = None) -> dict:
    thresholds = get_config(session, "signal_thresholds")
    q = session.query(Stock).filter_by(active=True)
    if codes:
        q = q.filter(Stock.code.in_([c.upper() for c in codes]))
    stocks = q.order_by(Stock.code).all()

    per_stock: dict[str, int] = {}
    for stock in stocks:
        try:
            per_stock[stock.code] = replay_stock(session, stock, days, thresholds)
        except Exception:
            logger.exception("replay failed for %s", stock.code)
            per_stock[stock.code] = -1

    fill_stats = fill_pending_returns(session)
    return {
        "stocks": len(stocks),
        "signals_added": sum(v for v in per_stock.values() if v > 0),
        "per_stock": per_stock,
        "returns": fill_stats,
    }
