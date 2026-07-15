from __future__ import annotations

import argparse
import json
from pathlib import Path

from third_model import config as model_config
from third_model.synthetic_replay import (
    DEFAULT_REPLAY_END,
    DEFAULT_REPLAY_START,
    DEFAULT_WARMUP_START,
    ReplayGenerationConfig,
    build_model_sensor_registry,
    generate_replay_dataset,
    parse_station_spec,
    validate_replay_dataset,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic PreDist-based raw and six-hour replay CSV shards."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=model_config.PROJECT_ROOT / "data/demo_replay/current",
    )
    parser.add_argument(
        "--sensor-manifest",
        type=Path,
        default=model_config.PROJECT_ROOT / "data/demo_replay/config/sensor_manifest.csv",
    )
    parser.add_argument("--raw-root", type=Path, default=model_config.SOURCE_RAW_ROOT)
    parser.add_argument(
        "--donor-windows",
        type=Path,
        default=model_config.TRAINABLE_WINDOWS_PATH,
    )
    parser.add_argument("--start", default=DEFAULT_WARMUP_START.isoformat())
    parser.add_argument("--replay-start", default=DEFAULT_REPLAY_START.isoformat())
    parser.add_argument("--end", default=DEFAULT_REPLAY_END.isoformat())
    parser.add_argument("--stations", default=None)
    parser.add_argument("--seed", type=int, default=20230710)
    parser.add_argument("--dataset-version", default="predist-synthetic-replay-v1")
    parser.add_argument("--fault-scenarios", type=int, default=18)
    parser.add_argument("--quality-scenarios", type=int, default=12)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Generate one visible six-hour window; defaults to station 1 unless --stations is changed.",
    )
    parser.add_argument(
        "--full-range",
        action="store_true",
        help="Use the fixed 2023-01-01 through 2026-01-08 production range.",
    )
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--run-inference-validation", action="store_true")
    parser.add_argument("--build-registry-only", action="store_true")
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if args.sample and args.full_range:
        parser.error("--sample and --full-range are mutually exclusive")
    if args.build_registry_only:
        target = args.output / "model_sensor_registry.csv"
        registry = build_model_sensor_registry(model_config.PROJECT_ROOT, output_path=target)
        print(json.dumps({"path": str(target), "sensor_count": len(registry)}, ensure_ascii=False))
        return
    if args.validate_only:
        result = validate_replay_dataset(
            args.output,
            project_root=model_config.PROJECT_ROOT,
            run_inference=args.run_inference_validation,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    start = args.start
    replay_start = args.replay_start
    end = args.end
    stations = args.stations or "1-31"
    fault_scenarios = args.fault_scenarios
    quality_scenarios = args.quality_scenarios
    if args.sample:
        start = DEFAULT_WARMUP_START.isoformat()
        replay_start = DEFAULT_REPLAY_START.isoformat()
        end = "2023-01-08T06:00:00+09:00"
        stations = args.stations or "1"
        fault_scenarios = 0
        quality_scenarios = 0
    elif args.full_range:
        start = DEFAULT_WARMUP_START.isoformat()
        replay_start = DEFAULT_REPLAY_START.isoformat()
        end = DEFAULT_REPLAY_END.isoformat()

    parsed_stations = parse_station_spec(stations)
    generation = ReplayGenerationConfig(
        project_root=model_config.PROJECT_ROOT,
        output_root=args.output,
        sensor_manifest_path=args.sensor_manifest,
        raw_root=args.raw_root,
        donor_windows_path=args.donor_windows,
        warmup_start=start,
        replay_start=replay_start,
        replay_end=end,
        stations=parsed_stations,
        seed=args.seed,
        dataset_version=args.dataset_version,
        fault_scenario_count=fault_scenarios,
        quality_scenario_count=quality_scenarios,
        overwrite=args.overwrite,
    )
    manifest = generate_replay_dataset(generation)
    is_full_range = (
        start == DEFAULT_WARMUP_START.isoformat()
        and replay_start == DEFAULT_REPLAY_START.isoformat()
        and end == DEFAULT_REPLAY_END.isoformat()
        and parsed_stations == tuple(range(1, 32))
    )
    result = validate_replay_dataset(
        args.output,
        project_root=model_config.PROJECT_ROOT,
        run_inference=args.run_inference_validation or is_full_range,
    )
    print(
        json.dumps(
            {
                "dataset_manifest": str(args.output / "dataset_manifest.json"),
                "dataset_version": manifest["dataset_version"],
                "raw_rows": result["raw_rows"],
                "window_rows": result["window_rows"],
                "inference": result["inference"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
