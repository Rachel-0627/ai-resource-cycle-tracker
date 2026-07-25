import json
from datetime import datetime, timedelta

from app.models import Announcement, Stock
from app.services.qualitative_mining_context import (
    build_qualitative_context,
    enrich_qualitative_context,
)


def _metrics(width, grade, unit="g/t", commodity="gold", depth=80, project="Bankan"):
    return {
        "intercepts": [
            {
                "width_m": width,
                "grade": grade,
                "unit": unit,
                "commodity": commodity,
                "depth_m": depth,
                "text": f"{width}m at {grade} {unit}",
            }
        ],
        "project": project,
        "commodities": [commodity],
    }


def _add_history(session, stock, values, project="Bankan", unit="g/t", commodity="gold", start=None):
    start = start or datetime(2026, 1, 1)
    for i, grade_thickness in enumerate(values):
        width = 10
        grade = grade_thickness / width
        session.add(
            Announcement(
                stock_id=stock.id,
                ann_id=f"hist-{project}-{unit}-{commodity}-{i}",
                headline="Historical drill result",
                ann_date=start + timedelta(days=i),
                url="https://example.com/history.pdf",
                price_sensitive=True,
                ann_type="DRILL_RESULTS",
                type_score=85,
                matched_keywords="[]",
                raw_payload="{}",
                ai_metrics=json.dumps(_metrics(width, grade, unit=unit, commodity=commodity, project=project)),
            )
        )
    session.commit()


def test_build_context_returns_insufficient_history_without_comparables(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    context = build_qualitative_context(db_session, "TST", _metrics(12, 3.5, depth=90))

    assert context is not None
    assert context["grade_thickness"] == 42
    assert context["depth_category"] == "shallow"
    assert context["interval_quality_label"] == "moderate"
    assert context["project_percentile"] is None
    assert context["trend_vs_previous"] == "insufficient_history"
    assert "project history unavailable; label based on absolute grade-thickness only" in context["reason"]
    assert "Stored project history is insufficient" in context["qualitative_assessment"]


def test_build_context_calculates_project_percentile(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan")

    context = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert context is not None
    assert context["grade_thickness"] == 45
    assert context["project_percentile"] == 80
    assert context["interval_quality_label"] == "strong"
    assert context["materiality_label"] == "high"
    assert context["trend_vs_previous"] == "improving"
    assert "announcement type is DRILL_RESULTS" in context["reason"]
    assert "price_sensitive is true" in context["reason"]


def test_build_context_materiality_requires_drill_result_and_price_sensitive(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan")

    not_drill = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Bankan"),
        ann_type="OTHER",
        price_sensitive=True,
    )
    not_sensitive = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=False,
    )
    deep = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=350, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert not_drill is not None
    assert not_sensitive is not None
    assert deep is not None
    assert not_drill["interval_quality_label"] == "strong"
    assert not_sensitive["interval_quality_label"] == "strong"
    assert deep["interval_quality_label"] == "strong"
    assert not_drill["materiality_label"] == "medium"
    assert not_sensitive["materiality_label"] == "medium"
    assert deep["materiality_label"] == "medium"


def test_build_context_materiality_is_low_for_weak_project_percentile(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [40, 50, 60, 70, 80], project="Bankan")

    context = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 3, depth=70, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert context is not None
    assert context["interval_quality_label"] == "weak"
    assert context["materiality_label"] == "low"


def test_build_context_qualitative_assessment_uses_neutral_template(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan")

    with_history = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )
    no_history = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Other"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert with_history is not None
    assert no_history is not None
    assert with_history["qualitative_assessment"] == (
        "This is a strong result in the project's stored history, with grade-thickness "
        "in the 80th percentile, shallow depth, and high materiality."
    )
    assert no_history["qualitative_assessment"] == (
        "Stored project history is insufficient; absolute grade-thickness and shallow depth "
        "support a conservative moderate interval label and medium materiality."
    )
    combined = f"{with_history['qualitative_assessment']} {no_history['qualitative_assessment']}".lower()
    for forbidden in ("buy", "sell", "share price", "upside", "investment advice", "major positive"):
        assert forbidden not in combined


def test_build_context_requires_minimum_project_history(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20], project="Bankan")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, project="Bankan"))

    assert context is not None
    assert context["project_percentile"] is None
    assert "insufficient project history" in context["reason"]


def test_build_context_project_percentile_and_trend_require_same_project(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Other")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, project="Bankan"))

    assert context is not None
    assert context["project_percentile"] is None
    assert context["trend_vs_previous"] == "insufficient_history"
    assert "insufficient project history" in context["reason"]


def test_build_context_project_percentile_requires_same_stock_code(db_session):
    current = Stock(code="TST", name="Test Resources", commodity="gold")
    other = Stock(code="OTH", name="Other Resources", commodity="gold")
    db_session.add_all([current, other])
    db_session.commit()
    _add_history(db_session, other, [10, 20, 30, 40, 50], project="Bankan")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, project="Bankan"))

    assert context is not None
    assert context["project_percentile"] is None
    assert "insufficient project history" in context["reason"]


def test_build_context_classifies_depth_boundaries(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    cases = [
        (None, "unknown"),
        (100, "shallow"),
        (101, "medium"),
        (300, "medium"),
        (301, "deep"),
    ]

    for depth, expected in cases:
        context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, depth=depth))

        assert context is not None
        assert context["depth_category"] == expected


def test_build_context_uses_conservative_absolute_quality_when_history_is_missing(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    exceptional = build_qualitative_context(db_session, "TST", _metrics(20, 6, depth=90))
    strong_deep = build_qualitative_context(db_session, "TST", _metrics(10, 6, depth=350))
    moderate_unknown = build_qualitative_context(db_session, "TST", _metrics(10, 3, depth=None))
    weak = build_qualitative_context(db_session, "TST", _metrics(10, 1, depth=80))

    assert exceptional is not None
    assert strong_deep is not None
    assert moderate_unknown is not None
    assert weak is not None
    assert exceptional["interval_quality_label"] == "exceptional"
    assert strong_deep["interval_quality_label"] == "moderate"
    assert moderate_unknown["interval_quality_label"] == "weak"
    assert weak["interval_quality_label"] == "weak"
    assert "project history unavailable; label based on absolute grade-thickness only" in exceptional["reason"]


def test_build_context_keeps_units_and_commodities_comparable(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan", unit="%", commodity="copper")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, unit="g/t", commodity="gold"))

    assert context is not None
    assert context["project_percentile"] is None
    assert context["interval_quality_label"] == "moderate"


def test_build_context_does_not_compare_same_commodity_different_unit(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan", unit="ppm", commodity="gold")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, unit="g/t", commodity="gold"))

    assert context is not None
    assert context["project_percentile"] is None
    assert context["interval_quality_label"] == "moderate"


def test_build_context_does_not_compare_same_unit_different_commodity(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="lithium")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan", unit="%", commodity="copper")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, unit="%", commodity="lithium"))

    assert context is not None
    assert context["project_percentile"] is None
    assert context["interval_quality_label"] == "moderate"


def test_build_context_detects_flat_and_deteriorating_trends(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [40, 42, 44, 46, 48], project="Bankan")

    flat = build_qualitative_context(db_session, "TST", _metrics(10, 4.4, project="Bankan"))
    weak = build_qualitative_context(db_session, "TST", _metrics(10, 3.0, project="Bankan"))

    assert flat is not None
    assert weak is not None
    assert flat["trend_vs_previous"] == "flat"
    assert weak["trend_vs_previous"] == "deteriorating"


def test_build_context_trend_uses_recent_project_history_only(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [5, 5, 5, 5, 5], project="Other")
    _add_history(db_session, stock, [10, 20, 100, 110, 120, 130], project="Bankan", start=datetime(2026, 2, 1))

    context = build_qualitative_context(db_session, "TST", _metrics(10, 11.5, project="Bankan"))

    assert context is not None
    assert context["trend_vs_previous"] == "flat"


def test_enrich_qualitative_context_adds_new_metrics_key(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    enriched = enrich_qualitative_context(db_session, "TST", _metrics(9, 5, depth=350))

    assert "qualitative_context" in enriched
    assert enriched["qualitative_context"]["grade_thickness"] == 45
    assert enriched["qualitative_context"]["depth_category"] == "deep"
