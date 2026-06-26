from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = ROOT / "PREPROCESSING" / "osj"

EXPERIMENTS = {
    "leadtime_improvements": "experiments/06_test/06_leadtime_improvement_experiments.py",
}


def run_script(script_name: str) -> int:
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"missing script: {script_path}")
    result = subprocess.run([sys.executable, str(script_path)], cwd=str(ROOT))
    return int(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grouped 06 leadtime experiments entrypoint")
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
