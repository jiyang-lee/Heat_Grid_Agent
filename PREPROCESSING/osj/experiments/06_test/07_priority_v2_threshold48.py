from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
PRIORITY_DIR = DATA_DIR / "ml_priority"
MODEL_DIR = PRIORITY_DIR / "models"

INPUT_PATH = PRIORITY_DIR / "priority_engine_scores_tuned.csv"
OUTPUT_PATH = PRIORITY_DIR / "priority_engine_scores_v2_threshold48.csv"
METADATA_PATH = MODEL_DIR / "priority_engine_v2_threshold48_metadata.json"

ENGINE_VERSION = "priority_engine_v2_threshold48"
LEVEL_THRESHOLDS = {"urgent": 70.0, "high": 48.0, "medium": 34.0}


def priority_level(score: float) -> str:
    if score >= LEVEL_THRESHOLDS["urgent"]:
        return "urgent"
    if score >= LEVEL_THRESHOLDS["high"]:
        return "high"
    if score >= LEVEL_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def main() -> None:
    PRIORITY_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_PATH)
    df["priority_level"] = pd.to_numeric(df["priority_score"], errors="coerce").fillna(0.0).map(priority_level)
    df["engine_version"] = ENGINE_VERSION
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    metadata = {
        "engine_version": ENGINE_VERSION,
        "input_path": str(INPUT_PATH),
        "output_path": str(OUTPUT_PATH),
        "level_thresholds": LEVEL_THRESHOLDS,
        "change_summary": [
            "priority score formula is unchanged from priority_engine_v2_rule_based_tuned",
            "high threshold changed from 52.0 to 48.0 based on holdout threshold sweep",
            "urgent and medium thresholds are unchanged",
        ],
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    print(OUTPUT_PATH)
    print(METADATA_PATH)
    print()
    print(df["priority_level"].value_counts().to_string())


if __name__ == "__main__":
    main()
