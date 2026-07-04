"""Signal detection — pure functions, shared verbatim by live pipeline and replay.

Rules (thresholds from app_config signal_thresholds):
- REL_VOL_SPIKE   rel_vol >= 3x AND strictly-up day AND turnover >= floor
                  (direction gate: heavy volume on a red day is distribution)
- BREAKOUT_252D   close > prior 252-day max close AND rel_vol >= 1.5 AND liquid
- BREAKOUT_60D    same on 60d, suppressed when the 252d fires the same day
- KEY_ANNOUNCEMENT  new announcement with base >= 70, or price-sensitive >= 60;
                  PLACEMENT / TRADING_HALT excluded unconditionally
- SCORE_CROSS_UP  cycle score crosses INTO the High Priority band (same
                  threshold as the label — one number, not two)

A breakout close already implies an up day (the prior window contains
yesterday's close), so breakouts need no explicit direction gate.
"""

from dataclasses import dataclass, field

from .classifier import KEY_ANNOUNCEMENT_EXCLUDED_TYPES
from .indicators import IndicatorResult


@dataclass(frozen=True)
class AnnouncementEvent:
    ann_id: str
    headline: str
    ann_type: str
    type_score: float
    price_sensitive: bool


@dataclass
class SignalCandidate:
    signal_type: str
    reason: str
    evidence: dict = field(default_factory=dict)


def detect_price_signals(ind: IndicatorResult, thresholds: dict) -> list[SignalCandidate]:
    out: list[SignalCandidate] = []
    liquid = ind.dollar_turnover >= float(thresholds.get("min_dollar_turnover", 50_000))
    up_day = ind.day_change_pct is not None and ind.day_change_pct > 0

    base_evidence = {
        "close": ind.close,
        "day_change_pct": round(ind.day_change_pct, 2) if ind.day_change_pct is not None else None,
        "rel_vol": round(ind.rel_vol, 2) if ind.rel_vol is not None else None,
        "dollar_turnover": round(ind.dollar_turnover),
    }

    if (
        ind.rel_vol is not None
        and ind.rel_vol >= float(thresholds.get("rel_vol_spike", 3.0))
        and up_day
        and liquid
    ):
        out.append(
            SignalCandidate(
                "REL_VOL_SPIKE",
                reason=(
                    f"Volume {ind.rel_vol:.1f}x the 20-day average "
                    f"on a +{ind.day_change_pct:.1f}% day"
                ),
                evidence={**base_evidence, "avg_volume_20": round(ind.avg_volume_20 or 0)},
            )
        )

    breakout_vol_ok = ind.rel_vol is not None and ind.rel_vol >= float(
        thresholds.get("breakout_rel_vol", 1.5)
    )
    if liquid and breakout_vol_ok:
        if ind.breakout_252:
            out.append(
                SignalCandidate(
                    "BREAKOUT_252D",
                    reason=f"New 252-day closing high on {ind.rel_vol:.1f}x volume",
                    evidence={**base_evidence, "window": 252},
                )
            )
        elif ind.breakout_60:
            out.append(
                SignalCandidate(
                    "BREAKOUT_60D",
                    reason=f"New 60-day closing high on {ind.rel_vol:.1f}x volume",
                    evidence={**base_evidence, "window": 60},
                )
            )
    return out


def detect_announcement_signal(
    new_announcements: list[AnnouncementEvent], thresholds: dict
) -> SignalCandidate | None:
    key_score = float(thresholds.get("key_announcement_score", 70))
    ps_score = float(thresholds.get("key_announcement_ps_score", 60))
    hits = [
        a
        for a in new_announcements
        if a.ann_type not in KEY_ANNOUNCEMENT_EXCLUDED_TYPES
        and (a.type_score >= key_score or (a.price_sensitive and a.type_score >= ps_score))
    ]
    if not hits:
        return None
    best = max(hits, key=lambda a: a.type_score)
    return SignalCandidate(
        "KEY_ANNOUNCEMENT",
        reason=f"{best.ann_type}: {best.headline[:80]}",
        evidence={
            "announcements": [
                {
                    "ann_id": a.ann_id,
                    "headline": a.headline[:100],
                    "type": a.ann_type,
                    "base": a.type_score,
                    "price_sensitive": a.price_sensitive,
                }
                for a in hits
            ]
        },
    )


def detect_score_cross(
    prev_cycle_score: float | None, today_cycle_score: float, thresholds: dict
) -> SignalCandidate | None:
    threshold = float(thresholds.get("score_cross", 75))
    if prev_cycle_score is None:
        return None
    if prev_cycle_score < threshold <= today_cycle_score:
        return SignalCandidate(
            "SCORE_CROSS_UP",
            reason=(
                f"Cycle Score crossed {threshold:.0f} "
                f"({prev_cycle_score:.1f} -> {today_cycle_score:.1f})"
            ),
            evidence={
                "prev_score": round(prev_cycle_score, 1),
                "today_score": round(today_cycle_score, 1),
                "threshold": threshold,
            },
        )
    return None
