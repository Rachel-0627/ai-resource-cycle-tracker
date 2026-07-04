"""Pure price/volume indicator functions — no I/O, shared by live pipeline and replay.

Conventions:
- Input is an ascending-date sequence of DailyBar; results describe the LAST bar.
- rel_vol compares today's volume against the mean of the PREVIOUS 20 bars
  (excluding today) and requires a full 20-bar history — partial averages are
  noisy for illiquid juniors, so insufficient history yields None.
- Breakouts compare today's close against the max close of the previous N bars
  (close-only: less noisy than intraday highs) and require the full window.
"""

from dataclasses import dataclass
from datetime import date
from typing import Sequence

REL_VOL_LOOKBACK = 20
BREAKOUT_WINDOWS = (20, 60, 252)


@dataclass(frozen=True)
class DailyBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class IndicatorResult:
    date: date
    close: float
    volume: int
    dollar_turnover: float
    prev_close: float | None = None
    day_change_pct: float | None = None
    avg_volume_20: float | None = None
    rel_vol: float | None = None
    breakout_20: bool = False
    breakout_60: bool = False
    breakout_252: bool = False
    consecutive_up_days: int = 0
    vol_trend: float | None = None  # MA5/MA20 of volume, including today


def compute_indicators(bars: Sequence[DailyBar]) -> IndicatorResult | None:
    if not bars:
        return None
    today = bars[-1]
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]

    result = IndicatorResult(
        date=today.date,
        close=today.close,
        volume=today.volume,
        dollar_turnover=today.close * today.volume,
    )

    if len(bars) >= 2:
        result.prev_close = bars[-2].close
        if result.prev_close:
            result.day_change_pct = (today.close / result.prev_close - 1) * 100

    # relative volume vs previous 20 bars (excluding today)
    if len(bars) >= REL_VOL_LOOKBACK + 1:
        window = volumes[-(REL_VOL_LOOKBACK + 1):-1]
        avg = sum(window) / REL_VOL_LOOKBACK
        result.avg_volume_20 = avg
        result.rel_vol = today.volume / avg if avg > 0 else None

    # close-only breakouts over full prior windows
    for window_len in BREAKOUT_WINDOWS:
        if len(bars) >= window_len + 1:
            prior_max = max(closes[-(window_len + 1):-1])
            setattr(result, f"breakout_{window_len}", today.close > prior_max)

    # consecutive up days (close vs previous close)
    up = 0
    for i in range(len(bars) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            up += 1
        else:
            break
    result.consecutive_up_days = up

    # volume trend MA5/MA20 (both including today)
    if len(bars) >= 20:
        ma5 = sum(volumes[-5:]) / 5
        ma20 = sum(volumes[-20:]) / 20
        result.vol_trend = ma5 / ma20 if ma20 > 0 else None

    return result
