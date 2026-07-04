"""Validate that every active watchlist ticker still trades on ASX (via yfinance).

Junior miners get acquired/delisted often — run this after seeding and replace
any ticker reported as DEAD before relying on the pipeline.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import yfinance as yf  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Stock  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as session:
        codes = [s.code for s in session.query(Stock).filter_by(active=True).all()]
    if not codes:
        print("watchlist is empty — run seed_watchlist.py first")
        return

    tickers = [f"{c}.AX" for c in codes]
    data = yf.download(tickers, period="5d", group_by="ticker", progress=False, threads=True)

    dead, alive = [], []
    for code, ticker in zip(codes, tickers):
        try:
            closes = data[ticker]["Close"].dropna()
        except KeyError:
            closes = []
        if len(closes) == 0:
            dead.append(code)
        else:
            alive.append(code)

    print(f"alive: {len(alive)} -> {', '.join(alive)}")
    if dead:
        print(f"DEAD ({len(dead)}): {', '.join(dead)}  <- replace these in the watchlist")
        sys.exit(1)
    print("all tickers OK")


if __name__ == "__main__":
    main()
