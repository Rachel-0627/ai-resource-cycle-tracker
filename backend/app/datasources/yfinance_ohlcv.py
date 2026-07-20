"""Daily OHLCV via yfinance. ASX tickers use the .AX suffix.

auto_adjust=True absorbs the share consolidations that are common among
juniors; rows with close<=0 are dropped and NaN volumes become 0.
"""

import logging
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

EMPTY = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
YFINANCE_CACHE_DIR = Path(tempfile.gettempdir()) / "ai-resource-cycle-tracker-yfinance-cache"
YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))


def fetch_daily(symbol: str, start: date | None = None, period: str = "2y") -> pd.DataFrame:
    """Fetch daily bars. `start` for incremental sync, else `period` backfill.

    Returns a DataFrame[date, open, high, low, close, volume] where `date` is a
    python date in the instrument's exchange timezone.
    """
    ticker = yf.Ticker(symbol)
    try:
        if start is not None:
            df = ticker.history(start=start, auto_adjust=True)
        else:
            df = ticker.history(period=period, auto_adjust=True)
    except Exception as exc:  # yfinance raises assorted internal errors
        logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return EMPTY.copy()
    if df is None or df.empty:
        return EMPTY.copy()

    df = df.reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    if "date" not in df.columns or "close" not in df.columns:
        return EMPTY.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["close"] > 0]
    if "volume" not in df.columns:
        df["volume"] = 0
    df["volume"] = df["volume"].fillna(0).astype("int64")
    for col in ("open", "high", "low"):
        if col not in df.columns:
            df[col] = df["close"]
    return df[["date", "open", "high", "low", "close", "volume"]]
