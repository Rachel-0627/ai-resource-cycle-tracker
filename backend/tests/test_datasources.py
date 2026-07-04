import json
from datetime import timezone

from app.datasources.asx_announcements import AsxJsonAnnouncementSource

from conftest import FIXTURES


def load_sample() -> dict:
    return json.loads((FIXTURES / "asx_announcements_sample.json").read_text())


def make_source() -> AsxJsonAnnouncementSource:
    return AsxJsonAnnouncementSource(
        base_url="https://asx.api.example.com/asx-research/1.0",
        access_token="testtoken",
    )


def test_parse_payload_extracts_fields():
    anns = make_source().parse_payload(load_sample())
    assert len(anns) == 3  # the date-less item is skipped

    first = anns[0]
    assert first.ann_id == "2924-03100001-6A1330001"
    assert first.headline == "High-Grade Drill Results Extend Mineralisation at Depth"
    assert first.price_sensitive is True
    assert first.ann_date.tzinfo is not None
    assert first.ann_date.astimezone(timezone.utc).hour == 0  # UTC preserved
    assert first.raw["announcementType"] == "PROGRESS REPORT"


def test_parse_payload_builds_file_url_when_missing():
    anns = make_source().parse_payload(load_sample())
    first = anns[0]
    assert first.url == (
        "https://asx.api.example.com/asx-research/1.0/file/"
        "2924-03100001-6A1330001?access_token=testtoken"
    )
    # explicit url kept as-is
    assert anns[1].url == "https://example.com/custom.pdf"


def test_parse_payload_respects_count():
    anns = make_source().parse_payload(load_sample(), count=1)
    assert len(anns) == 1


def test_parse_payload_empty():
    src = make_source()
    assert src.parse_payload({}) == []
    assert src.parse_payload({"data": None}) == []
    assert src.parse_payload({"data": {"items": None}}) == []
