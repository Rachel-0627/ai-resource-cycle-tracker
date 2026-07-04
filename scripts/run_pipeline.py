"""Run the full daily pipeline once from the CLI (first run backfills ~2y of bars)."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import logging  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from app.database import init_db  # noqa: E402
from app.services.pipeline import run_daily_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trigger", default="cli")
    args = parser.parse_args()

    init_db()
    stats = run_daily_pipeline(trigger=args.trigger)
    print(json.dumps({k: v for k, v in stats.items() if k != "per_stock"}, indent=2, ensure_ascii=False))
    top_signals = {k: v for k, v in stats.get("per_stock", {}).items() if v.get("signals")}
    if top_signals:
        print("stocks with new signals:", json.dumps(top_signals, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
