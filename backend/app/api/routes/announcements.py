from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...models import Announcement, Stock
from ...schemas import AnnouncementOut
from ..deps import get_db
from ..serializers import announcement_out

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("", response_model=list[AnnouncementOut])
def list_announcements(
    on_date: date | None = None,
    ann_type: str | None = None,
    code: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Announcement, Stock).join(Stock, Announcement.stock_id == Stock.id)
    if on_date:
        q = q.filter(
            Announcement.ann_date >= datetime.combine(on_date, datetime.min.time()),
            Announcement.ann_date
            < datetime.combine(on_date + timedelta(days=1), datetime.min.time()),
        )
    if ann_type:
        q = q.filter(Announcement.ann_type == ann_type)
    if code:
        q = q.filter(Stock.code == code.upper())
    rows = q.order_by(Announcement.ann_date.desc()).limit(min(limit, 500)).all()
    return [announcement_out(ann, stock.code) for ann, stock in rows]
