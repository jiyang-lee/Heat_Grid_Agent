from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from heatgrid_weather import build_daily_weather_summary  # noqa: E402
from heatgrid_weather.client import KmaApiError, SEJONG_ASOS_STATION_ID  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch KMA APIHub ASOS daily weather summary for HeatGrid reports.")
    parser.add_argument("--start-date", required=True, help="Start date, e.g. 2019-12-01")
    parser.add_argument("--end-date", required=True, help="End date, e.g. 2019-12-31")
    parser.add_argument("--station-id", default=SEJONG_ASOS_STATION_ID, help="KMA ASOS station id. Default: Sejong 239.")
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = build_daily_weather_summary(args.start_date, args.end_date, station_id=args.station_id)
    except KmaApiError as exc:
        print(f"daily_weather_summary_error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
