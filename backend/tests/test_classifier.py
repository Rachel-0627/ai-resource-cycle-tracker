import pytest

from app.analysis.classifier import classify


@pytest.mark.parametrize(
    ("headline", "expected_type", "expected_score"),
    [
        # drill results vs drilling updates — "starting to drill" is not "found something"
        ("High-Grade Drill Results Extend Mineralisation at Depth", "DRILL_RESULTS", 85),
        ("Outstanding Assays Confirm Shallow Mineralisation", "DRILL_RESULTS", 85),
        ("25m at 3.2 g/t Au from 48m", "DRILL_RESULTS", 85),
        ("Major Gold Discovery at Mandilla", "DRILL_RESULTS", 85),
        ("Drilling Commences at Bankan Gold Project", "DRILLING_UPDATE", 40),
        ("Drilling Update", "DRILLING_UPDATE", 40),
        ("Mobilisation of Rig to Site", "DRILLING_UPDATE", 40),
        # resource estimates outrank drill wording
        ("Maiden Resource Estimate following successful drilling", "JORC_MRE", 90),
        ("Updated JORC Mineral Resource", "JORC_MRE", 90),
        # studies
        ("Scoping Study Confirms Robust Economics", "STUDY", 80),
        ("DFS Delivers Strong NPV", "STUDY", 80),
        # deals
        ("Binding Offtake Agreement Signed", "OFFTAKE", 75),
        ("Farm-in Agreement with Rio Tinto", "JV_FARMIN", 70),
        # substantial holder three-state
        ("Becoming a substantial holder", "SUBSTANTIAL_HOLDER", 70),
        ("Change in substantial holding", "SUBSTANTIAL_HOLDER", 50),
        ("Ceasing to be a substantial holder", "SUBSTANTIAL_HOLDER", 20),
        # dilution / neutral attention events
        ("Completion of Placement", "PLACEMENT", 50),
        ("Share Purchase Plan Offer Booklet", "PLACEMENT", 50),
        ("Trading Halt", "TRADING_HALT", 55),
        # periodic
        ("Quarterly Activities Report", "QUARTERLY", 40),
        ("Appendix 5B Cash Flow Report", "QUARTERLY", 40),
        # fallthrough
        ("Notification of cessation of securities - DYL", "OTHER", 20),
        ("Investor Presentation", "OTHER", 20),
        ("Results of Annual General Meeting", "OTHER", 20),
        # company-name collision guard: bare "Discovery" must not classify
        ("Predictive Discovery Investor Presentation", "OTHER", 20),
    ],
)
def test_classify(headline, expected_type, expected_score):
    result = classify(headline)
    assert result.ann_type == expected_type, headline
    assert result.type_score == expected_score, headline


def test_classify_is_case_insensitive():
    assert classify("TRADING HALT").ann_type == "TRADING_HALT"
    assert classify("maiden resource ESTIMATE").ann_type == "JORC_MRE"


def test_classify_respects_word_boundaries():
    # "rig" inside "Bright" must not match DRILLING_UPDATE
    assert classify("Bright Prospects Ahead").ann_type == "OTHER"


def test_classify_records_matched_keywords():
    result = classify("High-Grade Drill Results Extend Mineralisation at Depth")
    assert "drill results" in result.matched_keywords
    assert "high-grade" in result.matched_keywords


def test_classify_empty():
    assert classify("").ann_type == "OTHER"
    assert classify(None).ann_type == "OTHER"
