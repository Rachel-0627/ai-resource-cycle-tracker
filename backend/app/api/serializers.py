import json

from ..models import Announcement, Signal, Stock
from ..schemas import AnnouncementOut, SignalOut, SignalReturnOut


def announcement_out(ann: Announcement, code: str) -> AnnouncementOut:
    return AnnouncementOut(
        id=ann.id,
        code=code,
        ann_id=ann.ann_id,
        headline=ann.headline,
        ann_date=ann.ann_date,
        url=ann.url,
        price_sensitive=ann.price_sensitive,
        ann_type=ann.ann_type,
        type_score=ann.type_score,
        matched_keywords=json.loads(ann.matched_keywords or "[]"),
        ai_summary=ann.ai_summary,
    )


def signal_out(sig: Signal, stock: Stock) -> SignalOut:
    returns = sorted(sig.returns, key=lambda r: r.horizon_days)
    return SignalOut(
        id=sig.id,
        code=stock.code,
        stock_name=stock.name,
        date=sig.date,
        signal_type=sig.signal_type,
        source=sig.source,
        label=sig.label,
        reason=sig.reason,
        evidence=json.loads(sig.evidence or "{}"),
        price_at_signal=sig.price_at_signal,
        cycle_score_at_signal=sig.cycle_score_at_signal,
        returns=[
            SignalReturnOut(
                horizon_days=r.horizon_days,
                entry_price=r.entry_price,
                return_pct=r.return_pct,
                benchmark_return_pct=r.benchmark_return_pct,
                status=r.status,
            )
            for r in returns
        ],
    )
