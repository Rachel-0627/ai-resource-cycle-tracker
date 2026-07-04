import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ so `app` imports

from app import models  # noqa: E402,F401  (register mappings before create_all)
from app.database import Base  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def next_weekday(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def make_bars(closes, volumes=None, start=date(2025, 1, 6)):
    """Build consecutive-weekday DailyBar sequences for indicator tests."""
    from app.analysis.indicators import DailyBar

    volumes = volumes if volumes is not None else [100_000] * len(closes)
    assert len(volumes) == len(closes)
    bars = []
    d = start
    for close, volume in zip(closes, volumes):
        bars.append(
            DailyBar(
                date=d,
                open=float(close),
                high=float(close),
                low=float(close),
                close=float(close),
                volume=int(volume),
            )
        )
        d = next_weekday(d)
    return bars
