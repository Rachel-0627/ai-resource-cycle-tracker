"""Historical context for structured mining announcement intercepts.

This module enriches deterministic extraction output with derived mining
context. It only uses stored announcement metrics; when there is not enough
comparable history, percentile/trend fields explicitly report insufficient
history rather than inventing a conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from statistics import median
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..models import Announcement, Stock

QUALITATIVE_CONTEXT_KEY = "qualitative_context"
MIN_PROJECT_HISTORY = 3
MIN_TREND_HISTORY = 3
MAX_TREND_HISTORY = 5
SHALLOW_DEPTH_MAX_M = 100.0
MEDIUM_DEPTH_MAX_M = 300.0
ABSOLUTE_EXCEPTIONAL_GRADE_THICKNESS = 100.0
ABSOLUTE_STRONG_GRADE_THICKNESS = 50.0
ABSOLUTE_MODERATE_GRADE_THICKNESS = 20.0


@dataclass(frozen=True)
class ComparableIntercept:
    grade_thickness: float
    project: str | None
    commodity: str
    unit: str
    announcement_id: int


def enrich_qualitative_context(
    session: Session,
    stock_code: str,
    metrics: dict[str, Any],
    ann_type: str | None = None,
    price_sensitive: bool | None = None,
) -> dict[str, Any]:
    """Return metrics with a qualitative_context object added when possible."""

    enriched = dict(metrics)
    context = build_qualitative_context(
        session,
        stock_code,
        metrics,
        ann_type=ann_type,
        price_sensitive=price_sensitive,
    )
    if context is not None:
        enriched[QUALITATIVE_CONTEXT_KEY] = context
    return enriched


def build_qualitative_context(
    session: Session,
    stock_code: str,
    metrics: dict[str, Any],
    ann_type: str | None = None,
    price_sensitive: bool | None = None,
) -> dict[str, Any] | None:
    """Build qualitative context for the primary extracted intercept.

    The primary intercept is the first item in metrics["intercepts"], matching
    the analyzer's sorted "best intercept first" contract.
    """

    intercept = _primary_intercept(metrics)
    if intercept is None:
        return None

    grade_thickness = _grade_thickness(intercept)
    depth_category = _depth_category(intercept.get("depth_m"))
    project = _clean_project(metrics.get("project"))
    commodity = _clean_text(intercept.get("commodity"))
    unit = _normal_unit(intercept.get("unit"))

    reason_parts = [
        f"grade-thickness is {grade_thickness:g}",
        f"depth category is {depth_category}",
    ]
    if ann_type:
        reason_parts.append(f"announcement type is {ann_type}")
    if price_sensitive is not None:
        reason_parts.append(f"price_sensitive is {str(price_sensitive).lower()}")

    comparable = _historical_intercepts(
        session=session,
        stock_code=stock_code,
        commodity=commodity,
        unit=unit,
    )
    project_values = [
        item.grade_thickness
        for item in comparable
        if project is not None and _same_project(item.project, project)
    ]
    project_percentile = _percentile(grade_thickness, project_values, MIN_PROJECT_HISTORY)
    if project is None:
        reason_parts.append("project unavailable")
    elif project_percentile is None:
        reason_parts.append("insufficient project history")

    trend = _trend_vs_previous(grade_thickness, project_values)
    if trend == "insufficient_history":
        reason_parts.append("insufficient prior comparable results for trend")

    quality = _interval_quality_label(
        project_percentile,
        grade_thickness,
        depth_category,
    )
    if project_percentile is None:
        reason_parts.append("project history unavailable; label based on absolute grade-thickness only")
    materiality = _materiality_label(
        quality,
        depth_category,
        project_percentile,
        ann_type=ann_type,
        price_sensitive=price_sensitive,
    )
    assessment = _qualitative_assessment(quality, materiality, project_percentile, depth_category)

    return {
        "grade_thickness": grade_thickness,
        "depth_category": depth_category,
        "interval_quality_label": quality,
        "project_percentile": project_percentile,
        "trend_vs_previous": trend,
        "materiality_label": materiality,
        "reason": "; ".join(reason_parts),
        "qualitative_assessment": assessment,
    }


def _primary_intercept(metrics: dict[str, Any]) -> dict[str, Any] | None:
    intercepts = metrics.get("intercepts")
    if not isinstance(intercepts, list) or not intercepts:
        return None
    first = intercepts[0]
    if not isinstance(first, dict):
        return None
    try:
        width = float(first["width_m"])
        grade = float(first["grade"])
    except (KeyError, TypeError, ValueError):
        return None
    unit = _normal_unit(first.get("unit"))
    commodity = _clean_text(first.get("commodity"))
    if width <= 0 or grade <= 0 or not unit or not commodity:
        return None
    return first


def _grade_thickness(intercept: dict[str, Any]) -> float:
    return round(float(intercept["width_m"]) * float(intercept["grade"]), 4)


def _depth_category(depth_m: Any) -> str:
    try:
        depth = float(depth_m)
    except (TypeError, ValueError):
        return "unknown"
    if depth <= SHALLOW_DEPTH_MAX_M:
        return "shallow"
    if depth <= MEDIUM_DEPTH_MAX_M:
        return "medium"
    return "deep"


def _historical_intercepts(
    session: Session,
    stock_code: str,
    commodity: str,
    unit: str,
) -> list[ComparableIntercept]:
    stock = session.query(Stock).filter(Stock.code == stock_code).first()
    if stock is None:
        return []

    rows = (
        session.query(Announcement)
        .filter(Announcement.stock_id == stock.id, Announcement.ai_metrics.isnot(None))
        .order_by(Announcement.ann_date.asc(), Announcement.id.asc())
        .all()
    )
    comparable: list[ComparableIntercept] = []
    for row in rows:
        data = _loads_metrics(row.ai_metrics)
        if not data:
            continue
        project = _clean_project(data.get("project"))
        for item in _iter_intercepts(data):
            if _clean_text(item.get("commodity")) != commodity:
                continue
            if _normal_unit(item.get("unit")) != unit:
                continue
            try:
                grade_thickness = _grade_thickness(item)
            except (KeyError, TypeError, ValueError):
                continue
            comparable.append(
                ComparableIntercept(
                    grade_thickness=grade_thickness,
                    project=project,
                    commodity=commodity,
                    unit=unit,
                    announcement_id=row.id,
                )
            )
    return comparable


def _loads_metrics(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _iter_intercepts(metrics: dict[str, Any]) -> Iterable[dict[str, Any]]:
    intercepts = metrics.get("intercepts")
    if not isinstance(intercepts, list):
        return []
    return [item for item in intercepts if isinstance(item, dict)]


def _percentile(value: float, history: list[float], min_samples: int) -> float | None:
    if len(history) < min_samples:
        return None
    count = sum(1 for item in history if item <= value)
    return round(100 * count / len(history), 1)


def _trend_vs_previous(value: float, history: list[float]) -> str:
    if len(history) < MIN_TREND_HISTORY:
        return "insufficient_history"
    baseline = median(history[-MAX_TREND_HISTORY:])
    if baseline <= 0:
        return "insufficient_history"
    ratio = value / baseline
    if ratio >= 1.15:
        return "improving"
    if ratio <= 0.85:
        return "deteriorating"
    return "flat"


def _interval_quality_label(
    project_percentile: float | None,
    grade_thickness: float,
    depth_category: str,
) -> str:
    if project_percentile is not None:
        if project_percentile >= 90:
            return "exceptional"
        if project_percentile >= 70:
            return "strong"
        if project_percentile >= 40:
            return "moderate"
        return "weak"

    label = _absolute_quality_label(grade_thickness)
    return _depth_adjusted_quality(label, depth_category)


def _absolute_quality_label(grade_thickness: float) -> str:
    if grade_thickness >= ABSOLUTE_EXCEPTIONAL_GRADE_THICKNESS:
        return "exceptional"
    if grade_thickness >= ABSOLUTE_STRONG_GRADE_THICKNESS:
        return "strong"
    if grade_thickness >= ABSOLUTE_MODERATE_GRADE_THICKNESS:
        return "moderate"
    return "weak"


def _depth_adjusted_quality(label: str, depth_category: str) -> str:
    if depth_category not in {"deep", "unknown"}:
        return label
    order = ["weak", "moderate", "strong", "exceptional"]
    try:
        index = order.index(label)
    except ValueError:
        return label
    return order[max(0, index - 1)]


def _materiality_label(
    quality: str,
    depth_category: str,
    project_percentile: float | None,
    ann_type: str | None = None,
    price_sensitive: bool | None = None,
) -> str:
    is_drill_result = (ann_type or "").upper() == "DRILL_RESULTS"
    if (
        quality in {"exceptional", "strong"}
        and project_percentile is not None
        and project_percentile >= 75
        and depth_category != "deep"
        and is_drill_result
        and price_sensitive is True
    ):
        return "high"
    if quality in {"strong", "moderate", "insufficient_history"}:
        return "medium"
    return "low"


def _qualitative_assessment(
    quality: str,
    materiality: str,
    project_percentile: float | None,
    depth_category: str,
) -> str:
    if quality == "insufficient_history":
        return "Insufficient stored project history to assess whether this result is strong or weak in project context."
    if project_percentile is None:
        return (
            f"Stored project history is insufficient; absolute grade-thickness and {depth_category} depth "
            f"support a conservative {quality} interval label and {materiality} materiality."
        )
    return (
        f"This is a {quality} result in the project's stored history, with grade-thickness "
        f"in the {project_percentile:g}th percentile, {depth_category} depth, and {materiality} materiality."
    )


def _same_project(left: str | None, right: str | None) -> bool:
    return bool(left and right and left.casefold() == right.casefold())


def _clean_project(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normal_unit(value: Any) -> str:
    return str(value or "").strip().lower()
