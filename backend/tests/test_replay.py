import pytest

from app.models import Signal, SignalReturn, Stock
from app.services.backtest import backtest_summary
from app.services.replay import run_replay

from test_backtest import add_price_bars, add_stock


def seed_spike_history(db_session, stock):
    """25 flat bars, a 4x-volume +10% spike, then 7 quiet drifting bars."""
    closes = [1.0] * 25 + [1.1] + [1.12, 1.15, 1.18, 1.20, 1.22, 1.232, 1.24]
    volumes = [100_000] * 25 + [400_000] + [100_000] * 7
    return add_price_bars(db_session, stock, closes, volumes=volumes)


def test_replay_detects_historical_spike(db_session):
    stock = add_stock(db_session, code="RPL")
    dates = seed_spike_history(db_session, stock)

    stats = run_replay(db_session, days=100)
    assert stats["signals_added"] == 1
    assert stats["per_stock"]["RPL"] == 1

    signal = db_session.query(Signal).one()
    assert signal.signal_type == "REL_VOL_SPIKE"
    assert signal.source == "replay"
    assert signal.label is None
    assert signal.cycle_score_at_signal is None
    assert signal.date == dates[25]  # the spike bar

    # 5d return filled from replayed bars: entry 1.12 (next bar), exit 1.232 -> +10%
    sr5 = db_session.query(SignalReturn).filter_by(horizon_days=5, status="filled").one()
    assert sr5.entry_price == pytest.approx(1.12)
    assert sr5.return_pct == pytest.approx(10.0)


def test_replay_is_idempotent(db_session):
    stock = add_stock(db_session, code="RPL")
    seed_spike_history(db_session, stock)

    first = run_replay(db_session, days=100)
    second = run_replay(db_session, days=100)
    assert first["signals_added"] == 1
    assert second["signals_added"] == 0
    assert db_session.query(Signal).count() == 1


def test_replay_does_not_pollute_label_stats(db_session):
    stock = add_stock(db_session, code="RPL")
    seed_spike_history(db_session, stock)
    run_replay(db_session, days=100)

    label_summary = backtest_summary(db_session, group_by="label")
    assert label_summary["total_signals"] == 0  # replay carries no label

    type_summary = backtest_summary(db_session, group_by="signal_type", source="replay")
    assert type_summary["total_signals"] == 1


def test_replay_skips_thin_history(db_session):
    stock = add_stock(db_session, code="THN")
    add_price_bars(db_session, stock, [1.0] * 10)  # < 21 bars
    stats = run_replay(db_session, days=100)
    assert stats["signals_added"] == 0
