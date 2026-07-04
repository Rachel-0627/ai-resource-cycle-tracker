import pytest

from app.analysis.indicators import compute_indicators

from conftest import make_bars


def test_empty_bars():
    assert compute_indicators([]) is None


def test_single_bar_has_only_basics():
    result = compute_indicators(make_bars([1.5], volumes=[10_000]))
    assert result.close == 1.5
    assert result.dollar_turnover == pytest.approx(15_000)
    assert result.prev_close is None
    assert result.day_change_pct is None
    assert result.rel_vol is None
    assert result.breakout_20 is False
    assert result.consecutive_up_days == 0


def test_rel_vol_exact_value():
    # 20 prior bars at 100k volume, today 500k -> rel_vol exactly 5.0
    bars = make_bars([1.0] * 20 + [1.1], volumes=[100_000] * 20 + [500_000])
    result = compute_indicators(bars)
    assert result.avg_volume_20 == pytest.approx(100_000)
    assert result.rel_vol == pytest.approx(5.0)
    assert result.day_change_pct == pytest.approx(10.0)
    assert result.dollar_turnover == pytest.approx(550_000)


def test_rel_vol_none_when_history_short():
    bars = make_bars([1.0] * 15, volumes=[100_000] * 15)
    assert compute_indicators(bars).rel_vol is None


def test_rel_vol_none_when_zombie_book():
    # zero average volume must not divide — flags insufficient liquidity upstream
    bars = make_bars([1.0] * 21, volumes=[0] * 20 + [50_000])
    result = compute_indicators(bars)
    assert result.avg_volume_20 == 0
    assert result.rel_vol is None


def test_breakout_20_requires_exceeding_not_equaling():
    up = make_bars([1.0] * 20 + [1.1])
    flat = make_bars([1.0] * 20 + [1.0])
    assert compute_indicators(up).breakout_20 is True
    assert compute_indicators(flat).breakout_20 is False
    # only 21 bars: the 60d window is not available yet
    assert compute_indicators(up).breakout_60 is False


def test_breakout_all_windows_with_full_history():
    bars = make_bars([1.0] * 252 + [1.5])
    result = compute_indicators(bars)
    assert result.breakout_20 and result.breakout_60 and result.breakout_252


def test_consecutive_up_days():
    assert compute_indicators(make_bars([1.0, 1.01, 1.02, 1.03])).consecutive_up_days == 3
    assert compute_indicators(make_bars([1.0, 1.0, 1.01])).consecutive_up_days == 1
    assert compute_indicators(make_bars([1.0, 1.02, 1.01])).consecutive_up_days == 0


def test_vol_trend_exact_value():
    # 15 bars at 100k then 5 bars at 300k: MA5=300k, MA20=150k -> 2.0
    bars = make_bars([1.0] * 20, volumes=[100_000] * 15 + [300_000] * 5)
    assert compute_indicators(bars).vol_trend == pytest.approx(2.0)


def test_vol_trend_none_when_no_volume():
    bars = make_bars([1.0] * 20, volumes=[0] * 20)
    assert compute_indicators(bars).vol_trend is None
