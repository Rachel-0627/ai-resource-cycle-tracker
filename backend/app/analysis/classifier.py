"""Rule-based ASX announcement classifier. First matching taxonomy entry wins.

Design notes:
- JORC_MRE outranks DRILL_RESULTS so "Maiden Resource Estimate following
  drilling" classifies as the stronger resource event.
- DRILL_RESULTS (assays/intercepts, base 85) is split from DRILLING_UPDATE
  (drilling commenced/underway, base 40) — starting to drill is a much weaker
  event than reporting mineralisation.
- PLACEMENT (50) and TRADING_HALT (55) are scored near-neutral: a raise is
  dilution and a halt is only a "something is coming" flag; rules cannot tell
  a strategic premium placement from a rescue raise.
- SUBSTANTIAL_HOLDER maps the "funds entering" stage of the resource cycle:
  becoming=70 / change=50 / ceasing=20.
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Classification:
    ann_type: str
    type_score: float
    matched_keywords: list[str] = field(default_factory=list)


def _compile(patterns: list[tuple[str, str]]) -> list[tuple[str, re.Pattern]]:
    return [(display, re.compile(regex, re.IGNORECASE)) for display, regex in patterns]


# (ann_type, base_score, [(display_keyword, regex), ...]) — order = priority
TAXONOMY: list[tuple[str, float, list[tuple[str, re.Pattern]]]] = [
    (
        "JORC_MRE",
        90,
        _compile([
            ("mineral resource", r"\bmineral resources?\b"),
            ("resource estimate", r"\bresource estimates?\b"),
            ("maiden resource", r"\bmaiden resource\b"),
            ("resource upgrade", r"\bresource upgrade\b"),
            ("ore reserve", r"\bore reserves?\b"),
            ("jorc", r"\bjorc\b"),
            ("mre", r"\bmre\b"),
        ]),
    ),
    (
        "STUDY",
        80,
        _compile([
            ("scoping study", r"\bscoping study\b"),
            ("pre-feasibility", r"\bpre[- ]feasibility\b"),
            ("feasibility study", r"\bfeasibility stud(y|ies)\b"),
            ("pfs", r"\bpfs\b"),
            ("dfs", r"\bdfs\b"),
            ("bfs", r"\bbfs\b"),
            ("definitive feasibility", r"\bdefinitive feasibility\b"),
        ]),
    ),
    (
        "DRILL_RESULTS",
        85,
        _compile([
            ("drill results", r"\bdrill(ing)? results?\b"),
            ("assay", r"\bassays?\b"),
            ("intercept", r"\bintercepts?\b"),
            ("intersect", r"\bintersect(s|ed|ion|ions)?\b"),
            ("g/t", r"\bg/t\b"),
            ("high-grade", r"\bhigh[- ]grade\b"),
            ("mineralisation", r"\bmineralisation\b|\bmineralization\b"),
            # qualified only — bare "discovery" collides with company names
            # like "Predictive Discovery"
            ("discovery", r"\b(new|major|significant|maiden|gold|copper|lithium|uranium|nickel) discover(y|ies)\b"),
        ]),
    ),
    (
        "DRILLING_UPDATE",
        40,
        _compile([
            ("drilling", r"\bdrilling\b"),
            ("drill program", r"\bdrill(ing)? program(me)?\b"),
            ("mobilisation", r"\bmobilis|\bmobiliz"),
            ("rig", r"\brigs?\b"),
        ]),
    ),
    (
        "OFFTAKE",
        75,
        _compile([
            ("offtake", r"\boff[- ]?takes?\b"),
            ("supply agreement", r"\bsupply agreements?\b"),
            ("sales agreement", r"\bsales agreements?\b"),
        ]),
    ),
    (
        "JV_FARMIN",
        70,
        _compile([
            ("joint venture", r"\bjoint ventures?\b"),
            ("farm-in", r"\bfarm[- ]?in\b"),
            ("farm-out", r"\bfarm[- ]?out\b"),
            ("earn-in", r"\bearn[- ]?in\b"),
            ("strategic partnership", r"\bstrategic partnerships?\b"),
            ("strategic investment", r"\bstrategic investments?\b"),
        ]),
    ),
    # SUBSTANTIAL_HOLDER: three entries, most specific first
    (
        "SUBSTANTIAL_HOLDER",
        20,
        _compile([("ceasing substantial holder", r"\bceasing to be a substantial (holder|shareholder)\b")]),
    ),
    (
        "SUBSTANTIAL_HOLDER",
        70,
        _compile([("becoming substantial holder", r"\bbecoming a substantial (holder|shareholder)\b")]),
    ),
    (
        "SUBSTANTIAL_HOLDER",
        50,
        _compile([
            ("substantial holding change", r"\bchange in substantial holding\b"),
            ("substantial holder notice", r"\bsubstantial (holder|holding|shareholder)\b"),
        ]),
    ),
    (
        "PLACEMENT",
        50,
        _compile([
            ("placement", r"\bplacements?\b"),
            ("capital raising", r"\bcapital rais(e|ing)\b"),
            ("entitlement offer", r"\bentitlement offers?\b"),
            ("rights issue", r"\brights issues?\b"),
            ("share purchase plan", r"\bshare purchase plan\b"),
            ("spp", r"\bspp\b"),
        ]),
    ),
    (
        "TRADING_HALT",
        55,
        _compile([
            ("trading halt", r"\btrading halt\b"),
            ("voluntary suspension", r"\bvoluntary suspension\b"),
            ("pause in trading", r"\bpause in trading\b"),
            ("suspension from quotation", r"\bsuspension from (official )?quotation\b"),
        ]),
    ),
    (
        "QUARTERLY",
        40,
        _compile([
            ("quarterly activities", r"\bquarterly activities\b"),
            ("quarterly report", r"\bquarterly (report|cashflow|cash flow)\b"),
            ("appendix 5b", r"\bappendix 5b\b"),
        ]),
    ),
]

OTHER = Classification(ann_type="OTHER", type_score=20.0)

# announcement types excluded from the KEY_ANNOUNCEMENT signal regardless of score
KEY_ANNOUNCEMENT_EXCLUDED_TYPES = {"PLACEMENT", "TRADING_HALT"}


def classify(headline: str) -> Classification:
    text = (headline or "").strip()
    if not text:
        return OTHER
    for ann_type, base_score, patterns in TAXONOMY:
        matched = [display for display, pattern in patterns if pattern.search(text)]
        if matched:
            return Classification(ann_type=ann_type, type_score=float(base_score), matched_keywords=matched)
    return OTHER
