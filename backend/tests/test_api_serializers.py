import json
from datetime import datetime

from app.api.serializers import announcement_out
from app.models import Announcement


def _announcement(ai_metrics=None):
    return Announcement(
        id=1,
        stock_id=1,
        ann_id="ann-1",
        headline="High-Grade Drill Results",
        ann_date=datetime(2026, 7, 22),
        url="https://example.com/ann.pdf",
        price_sensitive=True,
        ann_type="DRILL_RESULTS",
        type_score=85,
        matched_keywords=json.dumps(["drill results"]),
        raw_payload="{}",
        ai_summary="Reports 10m at 4.5g/t gold from 70m.",
        ai_metrics=ai_metrics,
    )


def test_announcement_out_exposes_ai_metrics_as_object():
    out = announcement_out(
        _announcement(
            json.dumps(
                {
                    "qualitative_context": {
                        "grade_thickness": 45,
                        "project_percentile": 80,
                        "trend_vs_previous": "improving",
                    }
                }
            )
        ),
        "TST",
    )

    assert out.ai_metrics == {
        "qualitative_context": {
            "grade_thickness": 45,
            "project_percentile": 80,
            "trend_vs_previous": "improving",
        }
    }


def test_announcement_out_returns_none_for_invalid_ai_metrics_json():
    out = announcement_out(_announcement("not json"), "TST")

    assert out.ai_metrics is None
