"""Upsert data/watchlist_seed.csv into the stocks table. Idempotent."""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Stock  # noqa: E402


def main() -> None:
    init_db()
    csv_path = ROOT / "data" / "watchlist_seed.csv"
    added, updated = 0, 0
    with SessionLocal() as session, open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["code"].strip().upper()
            stock = session.query(Stock).filter_by(code=code).one_or_none()
            if stock is None:
                session.add(
                    Stock(
                        code=code,
                        name=row["name"].strip(),
                        commodity=row["commodity"].strip(),
                        stage=row.get("stage", "explorer").strip(),
                        notes=row.get("notes", "").strip(),
                    )
                )
                added += 1
            else:
                stock.name = row["name"].strip()
                stock.commodity = row["commodity"].strip()
                stock.stage = row.get("stage", "explorer").strip()
                updated += 1
        session.commit()
    print(f"seed done: {added} added, {updated} updated")


if __name__ == "__main__":
    main()
