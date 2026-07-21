"""Fetch → classify → upsert announcements for one stock (+ AI-analyzer hook)."""

import json
import logging

from sqlalchemy.orm import Session

from ..analysis.ai_stub import (
    AnnouncementAnalyzer,
    AnnouncementDocumentFetcher,
    insight_metrics_with_document,
)
from ..analysis.classifier import classify
from ..config import market_tz
from ..datasources.base import AnnouncementSource
from ..models import Announcement, Stock

logger = logging.getLogger(__name__)


def sync_announcements(
    session: Session,
    stock: Stock,
    source: AnnouncementSource,
    analyzer: AnnouncementAnalyzer,
    count: int = 20,
    document_fetcher: AnnouncementDocumentFetcher | None = None,
) -> dict:
    """Returns {"new": n}. SourceBlockedError is NOT caught here — the pipeline
    handles degradation so it can mark the whole run, not just one stock."""
    raws = source.fetch(stock.code, count)
    new = 0
    for raw in raws:
        exists = (
            session.query(Announcement.id)
            .filter_by(stock_id=stock.id, ann_id=raw.ann_id)
            .first()
        )
        if exists:
            continue
        classification = classify(raw.headline)
        ann_date = raw.ann_date
        if ann_date.tzinfo is not None:
            # store naive local (Australia/Sydney) so "announcement day" aligns
            # with ASX trading dates
            ann_date = ann_date.astimezone(market_tz()).replace(tzinfo=None)
        announcement = Announcement(
            stock_id=stock.id,
            ann_id=raw.ann_id,
            headline=raw.headline,
            ann_date=ann_date,
            url=raw.url,
            price_sensitive=raw.price_sensitive,
            ann_type=classification.ann_type,
            type_score=classification.type_score,
            matched_keywords=json.dumps(classification.matched_keywords),
            raw_payload=json.dumps(raw.raw),
        )
        document = None
        if analyzer.requires_document_text:
            fetcher = document_fetcher or AnnouncementDocumentFetcher()
            document = fetcher.fetch(raw.url)
        insight = analyzer.analyze(
            raw.headline,
            classification.ann_type,
            body_text=document.text if document is not None else None,
            source_url=raw.url,
        )
        if insight is not None:
            announcement.ai_summary = insight.summary
            announcement.ai_metrics = json.dumps(insight_metrics_with_document(insight, document))
        session.add(announcement)
        new += 1
    session.commit()
    return {"new": new}
