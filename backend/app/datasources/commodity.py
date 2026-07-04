"""Commodity proxies and the backtest benchmark share the yfinance daily feed.

gold/copper use continuous futures (GC=F / HG=F); lithium/uranium/rare_earth
have no reliable futures on yfinance so equity-ETF proxies are used — a
documented limitation, acceptable at 10% Cycle Score weight.
"""

from datetime import date

import pandas as pd

from .yfinance_ohlcv import fetch_daily


def fetch_commodity_daily(instrument: str, start: date | None = None) -> pd.DataFrame:
    df = fetch_daily(instrument, start=start)
    return df[["date", "close"]]
