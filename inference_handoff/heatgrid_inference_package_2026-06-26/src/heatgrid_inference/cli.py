from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from heatgrid_inference.feature_engineering import (
    build_window_features_from_file,
    build_window_features_from_raw_root,
    load_configuration_table,
    load_event_history,
)
from heatgrid_inference.scoring import HeatGridScorer


def package_root_from_file() -> Path:
    return Path(__file__).resolve().parents[2]


def write_csv(frame: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, encoding="utf-8-sig")


def command_score_windowed(args: argparse.Namespace) -> None:
    scorer = HeatGridScorer(args.package_root)
    windows = pd.read_csv(args.input)
    scored = scorer.score_window_features(windows)
    write_csv(scored, args.output)
    print(args.output)


def command_score_raw_file(args: argparse.Namespace) -> None:
    package_root = Path(args.package_root)
    raw_root = Path(args.raw_root) if args.raw_root else None
    configuration = load_configuration_table(raw_root) if raw_root else pd.DataFrame()
    events = load_event_history(raw_root) if raw_root else pd.DataFrame()
    windows = build_window_features_from_file(
        args.input,
        configuration_table=configuration,
        event_history=events,
        manufacturer=args.manufacturer,
        substation_id=args.substation_id,
    )
    scorer = HeatGridScorer(package_root)
    scored = scorer.score_window_features(windows)
    write_csv(scored, args.output)
    print(args.output)


def command_score_raw_root(args: argparse.Namespace) -> None:
    windows = build_window_features_from_raw_root(args.raw_root)
    scorer = HeatGridScorer(args.package_root)
    scored = scorer.score_window_features(windows)
    write_csv(scored, args.output)
    print(args.output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HeatGrid inference handoff CLI")
    parser.add_argument(
        "--package-root",
        type=Path,
        default=package_root_from_file(),
        help="Root directory of this inference package",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    windowed = subparsers.add_parser("score-windowed", help="Score an existing trainable/window feature CSV")
    windowed.add_argument("--input", type=Path, required=True)
    windowed.add_argument("--output", type=Path, required=True)
    windowed.set_defaults(func=command_score_windowed)

    raw_file = subparsers.add_parser("score-raw-file", help="Window and score one operational raw CSV")
    raw_file.add_argument("--input", type=Path, required=True)
    raw_file.add_argument("--output", type=Path, required=True)
    raw_file.add_argument("--raw-root", type=Path, help="predist_v2 root for config/event context")
    raw_file.add_argument("--manufacturer", type=str, help="Override manufacturer if path cannot infer it")
    raw_file.add_argument("--substation-id", type=int, help="Override substation id if path cannot infer it")
    raw_file.set_defaults(func=command_score_raw_file)

    raw_root = subparsers.add_parser("score-raw-root", help="Window and score every operational CSV under raw root")
    raw_root.add_argument("--raw-root", type=Path, required=True)
    raw_root.add_argument("--output", type=Path, required=True)
    raw_root.set_defaults(func=command_score_raw_root)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
