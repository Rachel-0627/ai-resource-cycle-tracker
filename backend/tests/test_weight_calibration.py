from datetime import date, timedelta

import pytest

from app.models import ScoreSnapshot, SignalReturn
from app.services.config_service import set_config
from app.services.weight_calibration import calibrate_weights

from test_backtest import add_signal, add_stock


def add_snapshot(session, stock, d, funding, announcement, resource=50, commodity=50, risk=50):
    session.add(
        ScoreSnapshot(
            stock_id=stock.id,
            date=d,
            funding_score=funding,
            announcement_score=announcement,
            resource_score=resource,
            commodity_score=commodity,
            risk_score=risk,
            cycle_score=0.35 * funding + 0.30 * announcement + 0.20 * resource + 0.10 * commodity + 0.05 * risk,
            label="Monitor",
            components="{}",
        )
    )
    session.commit()


def fill_signal_return(session, signal, ret, bench=0.0, horizon=20):
    sr = session.query(SignalReturn).filter_by(signal_id=signal.id, horizon_days=horizon).one()
    sr.status = "filled"
    sr.entry_price = 1.0
    sr.return_pct = ret
    sr.benchmark_return_pct = bench
    session.commit()


def test_weight_calibration_recommends_predictive_subscore(db_session):
    stock = add_stock(db_session)
    start = date(2026, 1, 5)

    for i in range(12):
        d = start + timedelta(days=i)
        funding = 10 + i * 7
        announcement = 80 - i * 3
        add_snapshot(db_session, stock, d, funding=funding, announcement=announcement)
        sig = add_signal(
            db_session,
            stock,
            d,
            label="Monitor",
            cycle_score=50,
            horizons=(20,),
        )
        # Funding intentionally predicts the target; announcement moves the other way.
        fill_signal_return(db_session, sig, ret=i * 2.0, bench=0.0)

    result = calibrate_weights(db_session, horizon_days=20, target="excess", min_sample=10)

    assert result["sample_size"] == 12
    assert result["low_sample"] is False
    assert result["recommended_weights"]["funding"] > result["current_weights"]["funding"]
    assert result["recommended_weights"]["announcement"] < result["current_weights"]["announcement"]
    assert sum(result["recommended_weights"].values()) == pytest.approx(1.0)
    funding_diag = next(d for d in result["diagnostics"] if d["subscore"] == "funding")
    assert funding_diag["correlation"] > 0.99


def test_weight_calibration_keeps_current_weights_on_low_sample(db_session):
    stock = add_stock(db_session)
    set_config(db_session, "weights", {"funding": 0.4, "announcement": 0.25, "resource": 0.2, "commodity": 0.1, "risk": 0.05})
    d = date(2026, 1, 5)
    add_snapshot(db_session, stock, d, funding=90, announcement=20)
    sig = add_signal(db_session, stock, d, horizons=(20,))
    fill_signal_return(db_session, sig, ret=10, bench=1)

    result = calibrate_weights(db_session, horizon_days=20, target="excess", min_sample=10)

    assert result["sample_size"] == 1
    assert result["low_sample"] is True
    assert result["recommended_weights"] == result["current_weights"]


def test_weight_calibration_rejects_invalid_target(db_session):
    with pytest.raises(ValueError):
        calibrate_weights(db_session, target="alpha")
