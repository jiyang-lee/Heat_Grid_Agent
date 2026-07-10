from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from heatgrid_weather import build_weather_context  # noqa: E402
from heatgrid_weather.client import KmaApiError, SEJONG_ASOS_STATION_ID  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch KMA ASOS weather context for HeatGrid Agent.")
    parser.add_argument("--start", required=True, help="Window start, e.g. 2019-12-01 00:00:00")
    parser.add_argument("--end", required=True, help="Window end, e.g. 2019-12-01 06:00:00")
    parser.add_argument("--station-id", default=SEJONG_ASOS_STATION_ID, help="KMA ASOS station id. Default: Sejong 239.")
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        context = build_weather_context(args.start, args.end, station_id=args.station_id)
    except KmaApiError as exc:
        print(f"weather_context_error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    text = json.dumps(context, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
