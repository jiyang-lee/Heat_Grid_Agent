from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = ROOT / "PREPROCESSING" / "osj"

AUDITS = {
    "false_negative": "experiments/06_test/06_false_negative_audit.py",
    "false_negative_deep": "experiments/06_test/06_false_negative_deep_audit.py",
    "feature_importance": "experiments/06_test/06_feature_importance_audit.py",
    "group_calibration": "pipeline_scripts/06_risk_calibration.py",
    "drift_ablation": "experiments/06_test/06_drift_feature_ablation.py",
    "manufacturer2_sh_fp": "experiments/06_test/06_manufacturer2_sh_fp_audit.py",
}


def run_script(script_name: str) -> int:
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"missing script: {script_path}")
    result = subprocess.run([sys.executable, str(script_path)], cwd=str(ROOT))
    return int(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grouped 06 risk audit entrypoint")
    parser.add_argument("--list", action="store_true", help="List supported audits")
    parser.add_argument(
        "--run",
        nargs="+",
        choices=sorted(AUDITS) + ["all"],
        help="Run one or more audits, or all",
    )
    args = parser.parse_args()

    if args.list or not args.run:
        for name, script in AUDITS.items():
            print(f"{name}: {script}")
        return

    run_names = list(AUDITS) if "all" in args.run else args.run
    for name in run_names:
        print(f"[run] {name} -> {AUDITS[name]}")
        code = run_script(AUDITS[name])
        if code != 0:
            sys.exit(code)


if __name__ == "__main__":
    main()
