from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "PREPROCESSING" / "osj"

TARGETS = {
    "calibrated_official": "06_group_calibration.py",
    "promoted_candidate": "06_test/06_promoted_risk_model.py",
}


def run_script(script_name: str) -> int:
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"missing script: {script_path}")
    result = subprocess.run([sys.executable, str(script_path)], cwd=str(ROOT))
    return int(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonical 06 risk entrypoint")
    parser.add_argument(
        "--target",
        choices=sorted(TARGETS),
        default="calibrated_official",
        help="Risk artifact to build",
    )
    parser.add_argument("--list", action="store_true", help="List supported targets")
    args = parser.parse_args()

    if args.list:
        for name, script in TARGETS.items():
            print(f"{name}: {script}")
        return

    sys.exit(run_script(TARGETS[args.target]))


if __name__ == "__main__":
    main()
