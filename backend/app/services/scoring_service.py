"""Score one stock on its own latest bar and detect the day's signals."""

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..analysis.indicators import DailyBar, compute_indicators
from ..analysis.scoring import (
    ScoredAnnouncement,
    announcement_score,
    commodity_score,
    cycle_score,
    funding_score,
    label_for,
)
from ..analysis.signals import (
    AnnouncementEvent,
    detect_announcement_signal,
    detect_price_signals,
    detect_score_cross,
)
from ..models import Announcement, CommodityBar, PriceBar, ScoreSnapshot, Stock
from .signal_service import persist_signals

ANNOUNCEMENT_LOOKBACK_DAYS = 30


def load_bars(session: Session, stock: Stock) -> list[DailyBar]:
    rows = (
        session.query(PriceBar)
        .filter(PriceBar.stock_id == stock.id)
        .order_by(PriceBar.date)
        .all()
    )
    return [
        DailyBar(date=r.date, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for r in rows
    ]


def score_and_signal_stock(
    session: Session,
    stock: Stock,
    thresholds: dict,
    weights: dict,
    label_thresholds: dict,
    commodity_map: dict,
) -> dict:
    bars = load_bars(session, stock)
    ind = compute_indicators(bars)
    if ind is None:
        return {"skipped": "no_bars", "signals": 0}
    # each stock is evaluated on its OWN latest bar so one laggy ticker
    # doesn't stale-date the whole watchlist
    eval_date = ind.date

    funding, funding_comp = funding_score(ind, thresholds)

    ann_rows = (
        session.query(Announcement)
        .filter(
            Announcement.stock_id == stock.id,
            Announcement.ann_date
            >= datetime.combine(eval_date - timedelta(days=ANNOUNCEMENT_LOOKBACK_DAYS), datetime.min.time()),
        )
        .order_by(Announcement.ann_date.desc())
        .all()
    )
    scored_anns = [
        ScoredAnnouncement(
            headline=a.headline,
            ann_type=a.ann_type,
            type_score=a.type_score,
            ann_date=a.ann_date.date(),
            price_sensitive=a.price_sensitive,
        )
        for a in ann_rows
    ]
    announcement, ann_comp = announcement_score(scored_anns, eval_date)

    resource = stock.resource_score_override if stock.resource_score_override is not None else 50.0
    resource_comp = {
        "value": resource,
        "source": "manual_override" if stock.resource_score_override is not None else "neutral_default",
    }
    risk = stock.risk_score_override if stock.risk_score_override is not None else 50.0
    risk_comp = {
        "value": risk,
        "source": "manual_override" if stock.risk_score_override is not None else "neutral_default",
    }

    instrument = commodity_map.get(stock.commodity)
    closes = []
    if instrument:
        closes = (
            session.query(CommodityBar.date, CommodityBar.close)
            .filter(CommodityBar.instrument == instrument)
            .order_by(CommodityBar.date)
            .all()
        )
    commodity, commodity_comp = commodity_score(closes, eval_date)
    commodity_comp["instrument"] = instrument

    total = cycle_score(funding, announcement, resource, commodity, risk, weights)
    label = label_for(total, label_thresholds)

    prev_snap = (
        session.query(ScoreSnapshot)
        .filter(ScoreSnapshot.stock_id == stock.id, ScoreSnapshot.date < eval_date)
        .order_by(ScoreSnapshot.date.desc())
        .first()
    )

    components = json.dumps(
        {
            "funding": funding_comp,
            "announcement": ann_comp,
            "resource": resource_comp,
            "commodity": commodity_comp,
            "risk": risk_comp,
            "weights": weights,
        }
    )
    snapshot = (
        session.query(ScoreSnapshot)
        .filter_by(stock_id=stock.id, date=eval_date)
        .one_or_none()
    )
    if snapshot is None:
        snapshot = ScoreSnapshot(stock_id=stock.id, date=eval_date)
        session.add(snapshot)
    snapshot.funding_score = funding
    snapshot.announcement_score = announcement
    snapshot.resource_score = resource
    snapshot.commodity_score = commodity
    snapshot.risk_score = risk
    snapshot.cycle_score = total
    snapshot.label = label
    snapshot.components = components
    session.commit()

    # ---- signals for the evaluation day ----
    candidates = detect_price_signals(ind, thresholds)

    # "new" announcements: since the previous snapshot (covers weekend gaps),
    # capped by announcement_window_days; first run = evaluation day only.
    window_days = int(thresholds.get("announcement_window_days", 5))
    since = prev_snap.date if prev_snap else eval_date - timedelta(days=1)
    since = max(since, eval_date - timedelta(days=window_days))
    new_events = [
        AnnouncementEvent(
            ann_id=a.ann_id,
            headline=a.headline,
            ann_type=a.ann_type,
            type_score=a.type_score,
            price_sensitive=a.price_sensitive,
        )
        for a in ann_rows
        if since < a.ann_date.date() <= eval_date
    ]
    key_candidate = detect_announcement_signal(new_events, thresholds)
    if key_candidate:
        candidates.append(key_candidate)
    cross_candidate = detect_score_cross(
        prev_snap.cycle_score if prev_snap else None, total, thresholds
    )
    if cross_candidate:
        candidates.append(cross_candidate)

    added = persist_signals(
        session,
        stock,
        eval_date,
        candidates,
        price_at_signal=ind.close,
        source="live",
        label=label,
        cycle_score=total,
    )
    return {
        "signals": added,
        "eval_date": eval_date.isoformat(),
        "cycle_score": round(total, 1),
        "label": label,
    }
