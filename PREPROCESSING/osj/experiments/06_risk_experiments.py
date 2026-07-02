from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = ROOT / "PREPROCESSING" / "osj"

EXPERIMENTS = {
    "event_reencoding": "experiments/06_test/06_event_context_reencoding_experiment.py",
    "event_state": "experiments/06_test/06_event_context_state_experiment.py",
    "thermal": "experiments/06_test/06_thermal_feature_experiment.py",
    "state_thermal_combined": "experiments/06_test/06_state_thermal_combined_experiment.py",
    "weighting": "experiments/06_test/06_risk_weighting_experiment.py",
    "combined_feature": "experiments/06_test/06_combined_feature_experiment.py",
}


def run_script(script_name: str) -> int:
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"missing script: {script_path}")
    result = subprocess.run([sys.executable, str(script_path)], cwd=str(ROOT))
    return int(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grouped 06 risk experiments entrypoint")
    parser.add_argument("--list", action="store_true", help="List supported experiments")
    parser.add_argument(
        "--run",
        nargs="+",
        choices=sorted(EXPERIMENTS) + ["all"],
        help="Run one or more experiments, or all",
    )
    args = parser.parse_args()

    if args.list or not args.run:
        for name, script in EXPERIMENTS.items():
            print(f"{name}: {script}")
        return

    run_names = list(EXPERIMENTS) if "all" in args.run else args.run
    for name in run_names:
        print(f"[run] {name} -> {EXPERIMENTS[name]}")
        code = run_script(EXPERIMENTS[name])
        if code != 0:
            sys.exit(code)


if __name__ == "__main__":
    main()
