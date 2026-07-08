from __future__ import annotations

import argparse
import os

from . import config
from .anomaly import train_score_anomaly
from .best_bridge import build_merged_model_scores, materialize_best_scores, materialize_current_best_model_artifacts
from .data_io import build_raw_inventory, import_canonical_windows
from .m1_specialist import build_m1_specialist_outputs
from .m1_specialist_gates import score_m1_specialist_gates
from .operational import build_agent_card
from .retrain import retrain_current_best_source, retrain_m1_specialist_source, retrain_sources
from .validation import run_all_validations


STEP_FUNCTIONS = {
    "retrain_current_best": retrain_current_best_source,
    "retrain_m1_specialist": retrain_m1_specialist_source,
    "retrain_sources": retrain_sources,
    "raw": build_raw_inventory,
    "windows": import_canonical_windows,
    "model_artifacts": materialize_current_best_model_artifacts,
    "anomaly": train_score_anomaly,
    "best_scores": materialize_best_scores,
    "merge": build_merged_model_scores,
    "agent_card": build_agent_card,
    "m1_specialist_gates": score_m1_specialist_gates,
    "m1_specialist": build_m1_specialist_outputs,
    "validation": run_all_validations,
}

DEFAULT_STEPS = [
    "raw",
    "windows",
    "model_artifacts",
    "anomaly",
    "best_scores",
    "merge",
    "agent_card",
    "m1_specialist_gates",
    "m1_specialist",
    "validation",
]

FULL_RETRAIN_STEPS = [
    "raw",
    "windows",
    "model_artifacts",
    "anomaly",
    "retrain_current_best",
    "merge",
    "agent_card",
    "retrain_m1_specialist",
    "m1_specialist_gates",
    "m1_specialist",
    "validation",
]


def run_steps(steps: list[str]) -> None:
    if steps == ["all"]:
        selected = DEFAULT_STEPS
    elif steps == ["full_retrain"]:
        selected = FULL_RETRAIN_STEPS
    else:
        selected = steps
    refresh_timestamp = any(step.startswith("retrain") for step in selected)
    old_refresh = os.environ.get("THIRD_MODEL_REFRESH_RUN_TIMESTAMP")
    if refresh_timestamp and old_refresh is None:
        os.environ["THIRD_MODEL_REFRESH_RUN_TIMESTAMP"] = "1"
    try:
        for step in selected:
            if step not in STEP_FUNCTIONS:
                raise ValueError(f"Unknown step: {step}. Valid steps: all, full_retrain, {', '.join(STEP_FUNCTIONS)}")
            print(f"\n=== running {step} ===")
            result = STEP_FUNCTIONS[step]()
            if hasattr(result, "shape"):
                print(f"{step}: shape={result.shape}")
    finally:
        if refresh_timestamp and old_refresh is None:
            os.environ.pop("THIRD_MODEL_REFRESH_RUN_TIMESTAMP", None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run active M1 specialist HeatGrid pipeline.")
    parser.add_argument(
        "--steps",
        nargs="+",
        default=["all"],
        help=(
            "Pipeline steps: all, full_retrain, retrain_current_best, retrain_m1_specialist, "
            "retrain_sources, raw, windows, model_artifacts, anomaly, best_scores, merge, "
            "agent_card, m1_specialist_gates, m1_specialist, validation."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_steps(args.steps)


if __name__ == "__main__":
    main()
