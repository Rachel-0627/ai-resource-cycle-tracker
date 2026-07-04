"""One-off historical replay of price-based signals over backfilled bars."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import logging  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from app.database import SessionLocal, init_db  # noqa: E402
from app.services.replay import run_replay  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=400, help="trading days to replay")
    parser.add_argument("--codes", nargs="*", help="restrict to specific codes")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        stats = run_replay(session, days=args.days, codes=args.codes)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
