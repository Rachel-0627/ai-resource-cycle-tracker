"""Forward-return backtest.

Entry convention (no look-ahead): signals are produced AFTER the close, so the
entry price is the close of the FIRST trading day AFTER the signal date, and
horizon h means h bars after that entry. This measures "was the evening report
still worth acting on the next day" — the only honest reading of signal value.

Trading days are counted on the stock's own bar calendar (halts/holidays skip
naturally). Signals whose stock stops printing bars long enough are marked
`unavailable` and excluded from stats but counted, keeping survivorship
visible instead of silently dropped.
"""

import statistics
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import CommodityBar, PriceBar, Signal, SignalReturn
from .config_service import get_config

BUCKETS = ((0, 45, "0-45"), (45, 60, "45-60"), (60, 75, "60-75"), (75, 1000, "75-100"))
LOW_SAMPLE_N = 10


def _load_instrument_series(session: Session, instrument: str) -> tuple[list[date], list[float]]:
    rows = (
        session.query(CommodityBar.date, CommodityBar.close)
        .filter(CommodityBar.instrument == instrument)
        .order_by(CommodityBar.date)
        .all()
    )
    return [r[0] for r in rows], [r[1] for r in rows]


def _series_close_at_or_before(dates: list[date], closes: list[float], d: date) -> float | None:
    idx = bisect_right(dates, d) - 1
    return closes[idx] if idx >= 0 else None


def _benchmark_return(
    bench: tuple[list[date], list[float]], entry_date: date, exit_date: date
) -> float | None:
    dates, closes = bench
    start = _series_close_at_or_before(dates, closes, entry_date)
    end = _series_close_at_or_before(dates, closes, exit_date)
    if start is None or end is None or start <= 0:
        return None
    return (end / start - 1) * 100


def fill_pending_returns(session: Session, today: date | None = None) -> dict:
    today = today or date.today()
    rows = (
        session.query(SignalReturn, Signal)
        .join(Signal, SignalReturn.signal_id == Signal.id)
        .filter(SignalReturn.status == "pending")
        .all()
    )
    by_stock: dict[int, list[tuple[SignalReturn, Signal]]] = defaultdict(list)
    for sr, sig in rows:
        by_stock[sig.stock_id].append((sr, sig))

    bench = _load_instrument_series(session, get_config(session, "benchmark_instrument"))
    filled = unavailable = still_pending = 0

    for stock_id, items in by_stock.items():
        bars = (
            session.query(PriceBar.date, PriceBar.close)
            .filter(PriceBar.stock_id == stock_id)
            .order_by(PriceBar.date)
            .all()
        )
        dates = [b[0] for b in bars]
        closes = [b[1] for b in bars]
        last_bar_date = dates[-1] if dates else None

        for sr, sig in items:
            entry_idx = bisect_right(dates, sig.date)  # first bar strictly after signal day
            bars_after = len(dates) - entry_idx
            if bars_after >= sr.horizon_days + 1:
                entry_price = closes[entry_idx]
                exit_idx = entry_idx + sr.horizon_days
                sr.entry_price = entry_price
                sr.return_pct = (closes[exit_idx] / entry_price - 1) * 100
                sr.benchmark_return_pct = _benchmark_return(bench, dates[entry_idx], dates[exit_idx])
                sr.status = "filled"
                sr.filled_at = datetime.now(timezone.utc).replace(tzinfo=None)
                filled += 1
            else:
                calendar_elapsed = (today - sig.date).days
                stale = last_bar_date is None or (today - last_bar_date).days > 10
                if calendar_elapsed > sr.horizon_days * 2 and stale:
                    sr.status = "unavailable"  # delisted / long suspension
                    unavailable += 1
                else:
                    still_pending += 1
    session.commit()
    return {"filled": filled, "unavailable": unavailable, "pending": still_pending}


def _bucket_for(score: float | None) -> str:
    if score is None:
        return "n/a (replay)"
    for lo, hi, name in BUCKETS:
        if lo <= score < hi:
            return name
    return "n/a (replay)"


def _group_key(sig: Signal, group_by: str) -> str:
    if group_by == "label":
        return sig.label or "n/a"
    if group_by == "score_bucket":
        return _bucket_for(sig.cycle_score_at_signal)
    return sig.signal_type


def backtest_summary(session: Session, group_by: str = "signal_type", source: str = "all") -> dict:
    """Aggregate filled forward returns. Labels/scores only exist on live
    signals, so those groupings force source=live to avoid polluted stats."""
    if group_by not in ("signal_type", "label", "score_bucket"):
        raise ValueError(f"invalid group_by: {group_by}")
    if group_by in ("label", "score_bucket") and source == "all":
        source = "live"

    q = (
        session.query(SignalReturn, Signal)
        .join(Signal, SignalReturn.signal_id == Signal.id)
        .filter(SignalReturn.status.in_(("filled", "unavailable")))
    )
    if source != "all":
        q = q.filter(Signal.source == source)

    grouped: dict[str, dict[int, list[tuple[float, float | None]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    unavailable_by_group: dict[str, int] = defaultdict(int)
    signal_ids: set[int] = set()

    for sr, sig in q.all():
        key = _group_key(sig, group_by)
        if sr.status == "unavailable":
            unavailable_by_group[key] += 1
            continue
        signal_ids.add(sig.id)
        grouped[key][sr.horizon_days].append((sr.return_pct, sr.benchmark_return_pct))

    horizons = (5, 20, 60, 120)
    groups = []
    for key in sorted(set(grouped) | set(unavailable_by_group)):
        cells = []
        for horizon in horizons:
            pairs = grouped.get(key, {}).get(horizon, [])
            returns = [p[0] for p in pairs]
            excess = [p[0] - p[1] for p in pairs if p[1] is not None]
            if returns:
                cells.append(
                    {
                        "horizon_days": horizon,
                        "n": len(returns),
                        "win_rate": round(sum(1 for r in returns if r > 0) / len(returns), 3),
                        "avg": round(statistics.mean(returns), 2),
                        "median": round(statistics.median(returns), 2),
                        "max": round(max(returns), 2),
                        "min": round(min(returns), 2),
                        "avg_excess": round(statistics.mean(excess), 2) if excess else None,
                        "low_sample": len(returns) < LOW_SAMPLE_N,
                    }
                )
            else:
                cells.append({"horizon_days": horizon, "n": 0, "low_sample": True})
        groups.append({"group": key, "cells": cells, "unavailable": unavailable_by_group.get(key, 0)})

    return {
        "group_by": group_by,
        "source": source,
        "total_signals": len(signal_ids),
        "groups": groups,
    }
