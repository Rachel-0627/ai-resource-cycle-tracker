import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...models import DailyReport
from ...schemas import DailyReportOut
from ..deps import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


def _to_out(report: DailyReport) -> DailyReportOut:
    return DailyReportOut(
        report_date=report.report_date,
        content=json.loads(report.content_json or "{}"),
        pushed=report.pushed,
        pushed_at=report.pushed_at,
        push_error=report.push_error,
    )


@router.get("", response_model=list[DailyReportOut])
def list_reports(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.query(DailyReport).order_by(DailyReport.report_date.desc()).limit(limit).all()
    return [_to_out(r) for r in rows]


@router.get("/latest", response_model=DailyReportOut)
def latest_report(db: Session = Depends(get_db)):
    report = db.query(DailyReport).order_by(DailyReport.report_date.desc()).first()
    if report is None:
        raise HTTPException(status_code=404, detail="no reports yet — run the pipeline first")
    return _to_out(report)


@router.get("/{report_date}", response_model=DailyReportOut)
def report_by_date(report_date: date, db: Session = Depends(get_db)):
    report = db.query(DailyReport).filter_by(report_date=report_date).one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"no report for {report_date}")
    return _to_out(report)
