"""AI announcement analysis.

The default analyzer is no-op and makes no network or paid model calls. Full
text analyzers opt into document fetching, receive a bounded PDF/text excerpt,
and return a compact summary plus structured mining metrics.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
import json
import logging
import re
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)


class _AnnouncementHTMLTextExtractor(HTMLParser):
    """Extract readable document text while dropping common page chrome."""

    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template"}
    BOILERPLATE_TAGS = {"nav", "header", "footer", "aside", "form"}
    CONTENT_TAGS = {"article", "main"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._skip_stack: list[str] = []
        self._body_depth = 0
        self._content_depth = 0
        self._all_parts: list[str] = []
        self._content_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag == "body":
            self._body_depth += 1
        if tag in self.CONTENT_TAGS:
            self._content_depth += 1
        if self._should_skip(tag, attrs_dict):
            self._skip_depth += 1
            self._skip_stack.append(tag)
        if tag in self.BLOCK_TAGS:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.BLOCK_TAGS:
            self._append("\n")
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
            self._skip_depth -= 1
        if tag in self.CONTENT_TAGS and self._content_depth:
            self._content_depth -= 1
        if tag == "body" and self._body_depth:
            self._body_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._body_depth == 0 and self._content_depth == 0:
            return
        text = unescape(data).strip()
        if text:
            self._append(text)

    def text(self) -> str:
        content = self._normalize(" ".join(self._content_parts))
        if len(content) >= 200:
            return content
        return self._normalize(" ".join(self._all_parts))

    def _append(self, text: str) -> None:
        self._all_parts.append(text)
        if self._content_depth:
            self._content_parts.append(text)

    def _should_skip(self, tag: str, attrs: dict[str, str]) -> bool:
        if tag in self.SKIP_TAGS or tag in self.BOILERPLATE_TAGS:
            return True
        marker = " ".join([attrs.get("id", ""), attrs.get("class", ""), attrs.get("role", "")]).lower()
        return bool(
            re.search(
                r"\b(cookie|banner|breadcrumb|menu|navbar|pagination|sidebar|subscribe|share|social|modal)\b",
                marker,
            )
        )

    @staticmethod
    def _normalize(text: str) -> str:
        text = re.sub(r"\s+", " ", text or "")
        text = re.sub(r"\s+([,.;:%)])", r"\1", text)
        text = re.sub(r"([(])\s+", r"\1", text)
        return text.strip()


@dataclass
class AnnouncementInsight:
    summary: str
    metrics: dict = field(default_factory=dict)  # e.g. grade/width/depth extractions
    confidence: float = 0.0


@dataclass
class AnnouncementDocument:
    url: str
    text: str
    content_type: str = ""
    status: str = "ok"
    error: str | None = None


class AnnouncementDocumentFetcher:
    """Fetch and extract bounded text from announcement documents."""

    def __init__(
        self,
        get: Callable[..., httpx.Response] | None = None,
        timeout: float = 20.0,
        max_bytes: int = 5_000_000,
        max_chars: int = 20_000,
    ):
        self._get = get or httpx.get
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_chars = max_chars

    def fetch(self, url: str) -> AnnouncementDocument | None:
        if not url:
            return None
        try:
            response = self._get(url, timeout=self.timeout, follow_redirects=True)
            response.raise_for_status()
            content = response.content[: self.max_bytes]
            content_type = response.headers.get("content-type", "")
            text = self._extract_text(content, content_type)
            return AnnouncementDocument(
                url=url,
                text=self._clean_text(text)[: self.max_chars],
                content_type=content_type,
            )
        except Exception as exc:
            logger.warning("announcement document fetch failed for %s: %s", url, exc)
            return AnnouncementDocument(url=url, text="", status="error", error=str(exc))

    def _extract_text(self, content: bytes, content_type: str) -> str:
        content_type_lower = content_type.lower()
        looks_like_pdf = "pdf" in content_type_lower or content.startswith(b"%PDF")
        if looks_like_pdf:
            try:
                from pypdf import PdfReader

                reader = PdfReader(BytesIO(content))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as exc:
                logger.warning("PDF text extraction failed: %s", exc)
                return ""
        decoded = self._decode_text(content, content_type)
        if self._looks_like_html(decoded, content_type_lower):
            return self._extract_html_text(decoded)
        return decoded

    @staticmethod
    def _decode_text(content: bytes, content_type: str) -> str:
        charset_match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.IGNORECASE)
        encodings = [charset_match.group(1)] if charset_match else []
        encodings.extend(["utf-8", "latin-1"])
        for encoding in encodings:
            try:
                return content.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return content.decode("utf-8", errors="ignore")

    @staticmethod
    def _looks_like_html(text: str, content_type: str) -> bool:
        if "html" in content_type:
            return True
        return bool(re.search(r"<!doctype\s+html|<html\b|<body\b|<(article|main|p|div|br)\b", text[:2000], re.I))

    @staticmethod
    def _extract_html_text(html: str) -> str:
        parser = _AnnouncementHTMLTextExtractor()
        parser.feed(html or "")
        parser.close()
        return parser.text()

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()


class AnnouncementAnalyzer(ABC):
    requires_document_text: bool = False

    @abstractmethod
    def analyze(
        self,
        headline: str,
        ann_type: str,
        body_text: str | None = None,
        source_url: str | None = None,
    ) -> AnnouncementInsight | None:
        """Return None when there is nothing to add."""


class NoopAnalyzer(AnnouncementAnalyzer):
    def analyze(
        self,
        headline: str,
        ann_type: str,
        body_text: str | None = None,
        source_url: str | None = None,
    ) -> AnnouncementInsight | None:
        return None


class PaidCallsDisabledAnalyzer(AnnouncementAnalyzer):
    """Cost-safe placeholder when a paid analyzer is selected but not enabled."""

    def __init__(self, reason: str):
        self.reason = reason

    def analyze(
        self,
        headline: str,
        ann_type: str,
        body_text: str | None = None,
        source_url: str | None = None,
    ) -> AnnouncementInsight | None:
        logger.info("AI analyzer skipped: %s", self.reason)
        return None


class RuleBasedFullTextAnalyzer(AnnouncementAnalyzer):
    """Deterministic extraction for common mining announcement metrics."""

    requires_document_text = True

    COMMODITY_ALIASES = {
        "au": "gold",
        "gold": "gold",
        "cu": "copper",
        "copper": "copper",
        "li2o": "lithium",
        "lithium": "lithium",
        "u3o8": "uranium",
        "uranium": "uranium",
        "treo": "rare_earth",
        "ree": "rare_earth",
        "rare earth": "rare_earth",
    }
    INTERCEPT_RE = re.compile(
        r"(?P<width>\d+(?:\.\d+)?)\s*m\s*(?:@|at)\s*"
        r"(?P<grade>\d+(?:\.\d+)?)\s*(?P<unit>g/t|%|ppm)\s*"
        r"(?P<commodity>Au|gold|Cu|copper|Li2O|lithium|U3O8|uranium|TREO|REE|rare earth)?"
        r"(?:[^.;,\n]{0,60}?\b(?:from|at)\s*(?P<depth>\d+(?:\.\d+)?)\s*m)?",
        re.IGNORECASE,
    )
    DEPTH_RE = re.compile(r"\b(?:from|at)\s*(?P<depth>\d+(?:\.\d+)?)\s*m\b", re.IGNORECASE)
    PROJECT_RE = re.compile(
        r"\b(?:at|from|within|for)\s+(?:the\s+)?(?P<project>[A-Z][A-Za-z0-9 &'/-]{2,60}?)\s+Project\b"
    )

    def analyze(
        self,
        headline: str,
        ann_type: str,
        body_text: str | None = None,
        source_url: str | None = None,
    ) -> AnnouncementInsight | None:
        text = f"{headline or ''}\n{body_text or ''}".strip()
        metrics = self.extract_metrics(text)
        if not metrics["intercepts"] and not metrics.get("project"):
            return None

        if metrics["intercepts"]:
            best = metrics["intercepts"][0]
            commodity = best.get("commodity") or "mineralisation"
            depth = f" from {best['depth_m']:g}m" if best.get("depth_m") is not None else ""
            summary = (
                f"Reports {best['width_m']:g}m at {best['grade']:g}{best['unit']} "
                f"{commodity}{depth}."
            )
        else:
            summary = f"Mentions {metrics['project']} Project."

        metrics.update(
            {
                "provider": "rules",
                "source_url": source_url,
                "document_chars": len(body_text or ""),
            }
        )
        confidence = 0.7 if metrics["intercepts"] else 0.45
        return AnnouncementInsight(summary=summary[:240], metrics=metrics, confidence=confidence)

    @classmethod
    def extract_metrics(cls, text: str) -> dict[str, Any]:
        intercepts = []
        seen: set[tuple] = set()
        for match in cls.INTERCEPT_RE.finditer(text or ""):
            commodity_raw = (match.group("commodity") or "").lower()
            depth = match.group("depth")
            if depth is None:
                nearby = text[match.end() : match.end() + 80]
                depth_match = cls.DEPTH_RE.search(nearby)
                depth = depth_match.group("depth") if depth_match else None
            item = {
                "width_m": float(match.group("width")),
                "grade": float(match.group("grade")),
                "unit": match.group("unit"),
                "commodity": cls.COMMODITY_ALIASES.get(commodity_raw),
                "depth_m": float(depth) if depth is not None else None,
                "text": match.group(0).strip()[:180],
            }
            key = (item["width_m"], item["grade"], item["unit"].lower(), item["depth_m"])
            if key not in seen:
                intercepts.append(item)
                seen.add(key)

        intercepts.sort(
            key=lambda item: (item["width_m"] * item["grade"], item["width_m"]),
            reverse=True,
        )
        project_match = cls.PROJECT_RE.search(text or "")
        commodities = sorted({i["commodity"] for i in intercepts if i.get("commodity")})
        return {
            "intercepts": intercepts[:10],
            "project": project_match.group("project").strip() if project_match else None,
            "commodities": commodities,
        }


class ClaudeAnalyzer(AnnouncementAnalyzer):
    """Anthropic Messages API analyzer for announcement documents."""

    API_URL = "https://api.anthropic.com/v1/messages"
    requires_document_text = True

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 400,
        timeout: float = 20.0,
        post: Callable[..., httpx.Response] | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._post = post or httpx.post

    def analyze(
        self,
        headline: str,
        ann_type: str,
        body_text: str | None = None,
        source_url: str | None = None,
    ) -> AnnouncementInsight | None:
        if not headline.strip():
            return None
        body_text = (body_text or "").strip()
        context = body_text[:12_000] if body_text else "(document text unavailable)"

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "system": (
                "You analyze ASX resource-company announcements for a research dashboard. "
                "Return only compact JSON. Do not provide investment advice or buy/sell recommendations."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Analyze this ASX resource-company announcement.\n"
                        f"Rule classification: {ann_type}\n"
                        f"Headline: {headline}\n"
                        f"Document URL: {source_url or ''}\n"
                        f"Document text excerpt:\n{context}\n\n"
                        "Return JSON with keys: summary, metrics, confidence.\n"
                        "summary: one neutral sentence, max 180 characters.\n"
                        "metrics: object containing explicitly stated intercepts, grade, "
                        "width_m, depth_m, project, commodity, stage, resource tonnage/grade, "
                        "or deal terms. Use null or omit unknown values. Do not infer unstated facts.\n"
                        "confidence: number from 0 to 1 for extraction confidence."
                    ),
                }
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            response = self._post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = self._content_text(data)
            parsed = self._parse_json_object(text)
        except Exception as exc:
            logger.warning("Claude announcement analysis failed: %s", exc)
            return None

        summary = str(parsed.get("summary") or "").strip()
        if not summary:
            return None
        metrics = parsed.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        confidence = self._bounded_float(parsed.get("confidence"), default=0.0)
        metrics = {
            **metrics,
            "confidence": confidence,
            "provider": "anthropic",
            "model": self.model,
            "source_url": source_url,
            "document_chars": len(body_text),
        }
        return AnnouncementInsight(summary=summary[:240], metrics=metrics, confidence=confidence)

    @staticmethod
    def _content_text(data: dict[str, Any]) -> str:
        parts = data.get("content") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        return "\n".join(texts).strip()

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return {}
            value = json.loads(text[start : end + 1])
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _bounded_float(value: Any, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, numeric))


def get_analyzer(name: str) -> AnnouncementAnalyzer:
    if name == "noop":
        return NoopAnalyzer()
    if name == "rules_fulltext":
        return RuleBasedFullTextAnalyzer()
    if name == "claude":
        from ..config import settings

        if not settings.ai_analyzer_allow_paid_calls:
            return PaidCallsDisabledAnalyzer("AI_ANALYZER_ALLOW_PAID_CALLS is false")
        if not settings.anthropic_api_key:
            return PaidCallsDisabledAnalyzer("ANTHROPIC_API_KEY is empty")
        return ClaudeAnalyzer(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
    raise ValueError(f"unknown ai analyzer: {name}")


def insight_metrics_with_document(
    insight: AnnouncementInsight, document: AnnouncementDocument | None
) -> dict:
    metrics = dict(insight.metrics)
    if document is not None:
        metrics["document"] = asdict(document)
        metrics["document"]["text"] = ""
    return metrics
