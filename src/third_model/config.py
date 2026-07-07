from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_SCOPE = "m1_specialist"
M1_MANUFACTURER = os.environ.get("THIRD_MODEL_M1_MANUFACTURER", "manufacturer 1")
CSV_FLOAT_FORMAT = "%.12g"
CSV_LINE_TERMINATOR = "\n"

def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _candidate_anchors() -> list[Path]:
    anchors: list[Path] = []
    for base in [PROJECT_ROOT, Path.cwd().resolve()]:
        anchors.extend([base, *base.parents[:5]])
    unique: list[Path] = []
    seen: set[str] = set()
    for anchor in anchors:
        key = str(anchor).lower()
        if key not in seen:
            seen.add(key)
            unique.append(anchor)
    return unique


def _discover_source_best_root() -> Path:
    env_path = _env_path("THIRD_MODEL_SOURCE_BEST_ROOT")
    if env_path is not None:
        return env_path
    candidates: list[Path] = []
    for anchor in _candidate_anchors():
        candidates.extend(
            [
                anchor / "best",
                anchor / "HeatGrid_Agent" / "best",
            ]
        )
    for candidate in candidates:
        if (candidate / "output").exists() and (candidate / "data").exists():
            return candidate.resolve()
    return PROJECT_ROOT / "_external" / "current_best_unavailable"


def _discover_third_project_root() -> Path:
    env_path = _env_path("THIRD_MODEL_3RD_PROJECT_ROOT")
    if env_path is not None:
        return env_path
    candidates: list[Path] = []
    for anchor in _candidate_anchors():
        candidates.extend(
            [
                anchor / "3rd_project_for_ML-main" / "3rd_project_for_ML-main",
                anchor / "3rd_project_for_ML-main",
            ]
        )
    for candidate in candidates:
        if candidate.exists() and any(p.is_dir() and p.name.startswith("08_") for p in candidate.iterdir()):
            return candidate.resolve()
    return PROJECT_ROOT / "_external" / "m1_specialist_source_unavailable"


def path_label(path: object, env_var: str | None = None) -> str:
    path_obj = Path(path)
    if env_var and _env_path(env_var) == path_obj.resolve():
        return f"${env_var}"
    try:
        return path_obj.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        pass
    try:
        return (Path("..") / path_obj.resolve().relative_to(PROJECT_ROOT.resolve().parent)).as_posix()
    except ValueError:
        return path_obj.as_posix()


# Source project discovery. Env var wins, then sibling project auto-discovery, then packaged artifacts.
SOURCE_BEST_ROOT = _discover_source_best_root()
SOURCE_RAW_ROOT = SOURCE_BEST_ROOT / "data" / "raw_data" / "predist_v2"
SOURCE_FEATURE_DIR = SOURCE_BEST_ROOT / "data" / "processed" / "ml_features"
SOURCE_OUTPUT_DIR = SOURCE_BEST_ROOT / "output"
SOURCE_MODEL_DIR = SOURCE_BEST_ROOT / "models"

def _discover_current_best_python() -> Path:
    env_path = _env_path("THIRD_MODEL_CURRENT_BEST_PYTHON")
    if env_path is not None:
        return env_path
    candidates = [
        SOURCE_BEST_ROOT / ".venv" / "Scripts" / "python.exe",
        SOURCE_BEST_ROOT.parent / ".venv" / "Scripts" / "python.exe",
        SOURCE_BEST_ROOT / ".venv" / "bin" / "python",
        SOURCE_BEST_ROOT.parent / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return Path(sys.executable).resolve()


CURRENT_BEST_PYTHON_PATH = Path(_discover_current_best_python())

DATA_DIR = PROJECT_ROOT / "data"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = PROJECT_ROOT / "output"
REPORT_DIR = OUTPUT_DIR / "reports"
RETRAIN_LOG_DIR = REPORT_DIR / "retrain_logs"
MODEL_DIR = PROJECT_ROOT / "models"
ANOMALY_MODEL_DIR = MODEL_DIR / "anomaly"
RISK_MODEL_DIR = MODEL_DIR / "risk"
LEADTIME_MODEL_DIR = MODEL_DIR / "leadtime"
PRIORITY_MODEL_DIR = MODEL_DIR / "priority"
M1_SPECIALIST_MODEL_DIR = MODEL_DIR / "m1_specialist"
MODEL_ARTIFACTS_METADATA_PATH = MODEL_DIR / "model_artifacts_metadata.json"
SOURCE_RETRAIN_METADATA_PATH = REPORT_DIR / "source_retrain_metadata.json"
M1_SOURCE_RETRAIN_METADATA_PATH = REPORT_DIR / "m1_source_retrain_metadata.json"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
CURRENT_BEST_ARTIFACT_DIR = ARTIFACT_DIR / "current_best"
CURRENT_BEST_SOURCE_SCORE_DIR = CURRENT_BEST_ARTIFACT_DIR / "source_score_outputs"
CURRENT_BEST_MODEL_METADATA_DIR = CURRENT_BEST_ARTIFACT_DIR / "model_metadata"

RAW_INVENTORY_PATH = INTERIM_DIR / "raw_inventory.csv"
RAW_SCHEMA_PATH = INTERIM_DIR / "raw_schema_summary.csv"
TRAINABLE_WINDOWS_PATH = PROCESSED_DIR / "trainable_windows.csv"
FEATURE_COLUMNS_PATH = PROCESSED_DIR / "feature_columns.csv"
IMPUTATION_VALUES_PATH = PROCESSED_DIR / "imputation_values.csv"

ANOMALY_SCORES_PATH = OUTPUT_DIR / "anomaly_scores.csv"
ANOMALY_METRICS_PATH = OUTPUT_DIR / "anomaly_metrics.csv"
ANOMALY_METADATA_PATH = ANOMALY_MODEL_DIR / "anomaly_metadata.json"
ANOMALY_SCALER_PATH = ANOMALY_MODEL_DIR / "standard_scaler.joblib"
IFOREST_MODEL_PATH = ANOMALY_MODEL_DIR / "isolation_forest.joblib"
MAHALANOBIS_MODEL_PATH = ANOMALY_MODEL_DIR / "mahalanobis_ledoitwolf.joblib"

M1_SPECIALIST_COMPACT13_FEATURES_PATH = OUTPUT_DIR / "m1_specialist_compact13_features.csv"
M1_SPECIALIST_GATE_SCORES_PATH = OUTPUT_DIR / "m1_specialist_gate_scores.csv"
M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH = OUTPUT_DIR / "agent" / "m1_specialist_parallel_agent_card.csv"
M1_SPECIALIST_GATE_METADATA_PATH = M1_SPECIALIST_MODEL_DIR / "m1_specialist_gate_metadata.json"
M1_SPECIALIST_PYTHON_PATH = Path(
    os.environ.get(
        "THIRD_MODEL_M1_SPECIALIST_PYTHON",
        sys.executable,
    )
)
THIRD_PROJECT_ROOT = Path(
    _discover_third_project_root()
)

RISK_SCORES_PATH = OUTPUT_DIR / "risk_scores.csv"
LEADTIME_SCORES_PATH = OUTPUT_DIR / "leadtime_scores.csv"
PRIORITY_SCORES_PATH = OUTPUT_DIR / "priority_scores.csv"
MERGED_SCORES_PATH = OUTPUT_DIR / "merged_model_scores.csv"
AGENT_CARD_PATH = OUTPUT_DIR / "agent_priority_card.csv"
STATE_CARD_SCHEMA_PATH = OUTPUT_DIR / "agent_state_card_schema.json"
M1_SPECIALIST_SCORES_PATH = OUTPUT_DIR / "m1_specialist_scores.csv"
M1_SPECIALIST_AGENT_CARD_PATH = OUTPUT_DIR / "agent" / "m1_agent_priority_card.csv"
M1_SPECIALIST_COMPARISON_PATH = REPORT_DIR / "m1_specialist_vs_current_best_comparison.csv"
M1_SPECIALIST_REPORT_PATH = REPORT_DIR / "m1_specialist_report.md"
M1_SCOPE_REPORT_PATH = REPORT_DIR / "m1_scope_audit.md"
AGENT_CARD_COLUMN_DICTIONARY_PATH = OUTPUT_DIR / "agent" / "agent_card_column_dictionary_ko.csv"
AGENT_CARD_COLUMN_GROUPS_PATH = OUTPUT_DIR / "agent" / "agent_card_column_groups_ko.csv"
AGENT_CARD_COLUMN_GROUPS_MD_PATH = OUTPUT_DIR / "agent" / "agent_card_column_groups_ko.md"
AGENT_CARD_VALUE_MAPPING_PATH = OUTPUT_DIR / "agent" / "agent_card_value_mapping_ko.md"

THRESHOLD_SWEEP_PATH = REPORT_DIR / "threshold_sweep.csv"
ABLATION_SUMMARY_PATH = REPORT_DIR / "ablation_summary.csv"
ABLATION_SUMMARY_MD_PATH = REPORT_DIR / "ablation_summary.md"
PRIORITY_SENSITIVITY_PATH = REPORT_DIR / "priority_weight_sensitivity.csv"
HARD_NORMAL_AUDIT_PATH = REPORT_DIR / "hard_normal_audit.csv"
ANOMALY_CRITICALITY_SWEEP_PATH = REPORT_DIR / "anomaly_criticality_threshold_sweep.csv"
ANOMALY_IF_MAHALANOBIS_GRID_PATH = REPORT_DIR / "anomaly_if_mahalanobis_policy_grid.csv"
HYBRID_WEIGHT_SWEEP_PATH = REPORT_DIR / "hybrid_weight_sweep.csv"
HYBRID_WEIGHT_SELECTION_SUMMARY_PATH = REPORT_DIR / "hybrid_weight_selection_summary.csv"
HYBRID_065_VS_072_METRIC_DELTA_PATH = REPORT_DIR / "hybrid_065_vs_072_metric_delta.csv"
HYBRID_065_VS_072_LEVEL_TRANSITION_PATH = REPORT_DIR / "hybrid_065_vs_072_level_transition.csv"
HYBRID_065_VS_072_CHANGED_ROWS_PATH = REPORT_DIR / "hybrid_065_vs_072_changed_rows.csv"
PRIORITY_COMPONENT_SUMMARY_PATH = REPORT_DIR / "priority_engine_component_summary.csv"
ROW_FLOW_SUMMARY_PATH = REPORT_DIR / "row_flow_summary.csv"
KEY_COVERAGE_BY_ARTIFACT_PATH = REPORT_DIR / "key_coverage_by_artifact.csv"
RISK_LEVEL_ACTUAL_SUMMARY_PATH = REPORT_DIR / "risk_level_actual_summary.csv"
RISK_THRESHOLD_ACTUAL_VALUES_PATH = REPORT_DIR / "risk_threshold_actual_values.csv"
M1_GATE_THRESHOLD_SWEEP_PATH = REPORT_DIR / "m1_gate_threshold_sweep.csv"
M1_GATE_SELECTED_THRESHOLD_SUMMARY_PATH = REPORT_DIR / "m1_gate_selected_threshold_summary.csv"
M1_GATE_THRESHOLD_REFERENCE_PATH = REPORT_DIR / "m1_gate_threshold_reference.csv"
M1_SPECIALIST_PRIORITY_WEIGHT_ABLATION_PATH = REPORT_DIR / "m1_specialist_priority_weight_ablation.csv"
M1_SPECIALIST_PRIORITY_WEIGHT_GRID_PATH = REPORT_DIR / "m1_specialist_priority_weight_grid.csv"
FAULT_GROUP_WEIGHT_SUMMARY_PATH = REPORT_DIR / "fault_group_weight_summary.csv"
LEVEL_CALIBRATION_FPR_CAP_SWEEP_PATH = REPORT_DIR / "level_calibration_fpr_cap_sweep.csv"
HYBRID_SELECTED_WEIGHT_COMPARISON_PATH = REPORT_DIR / "hybrid_selected_weight_comparison.csv"
ROW_RECONCILIATION_PATH = REPORT_DIR / "row_reconciliation.csv"
MISSING_AGENT_WINDOWS_PATH = REPORT_DIR / "missing_agent_windows.csv"
PIPELINE_RUN_METADATA_PATH = REPORT_DIR / "pipeline_run_metadata.json"
FINAL_VALIDATION_MD_PATH = REPORT_DIR / "final_validation_report.md"

SOURCE_TRAINABLE_WINDOWS_PATH = SOURCE_FEATURE_DIR / "trainable_windows.csv"
SOURCE_FEATURE_COLUMNS_PATH = SOURCE_FEATURE_DIR / "feature_columns.csv"
SOURCE_IMPUTATION_VALUES_PATH = SOURCE_FEATURE_DIR / "imputation_values.csv"

SOURCE_ANOMALY_METADATA_PATH = SOURCE_MODEL_DIR / "anomaly" / "anomaly_ensemble_metadata.json"
SOURCE_RISK_MODEL_PATH = SOURCE_MODEL_DIR / "risk" / "risk_model_best.joblib"
SOURCE_RISK_METADATA_PATH = SOURCE_MODEL_DIR / "risk" / "risk_model_best_metadata.json"
SOURCE_LEADTIME_MODEL_PATH = SOURCE_MODEL_DIR / "leadtime" / "leadtime_model_best.joblib"
SOURCE_LEADTIME_METADATA_PATH = SOURCE_MODEL_DIR / "leadtime" / "leadtime_model_best_metadata.json"
SOURCE_PRIORITY_METADATA_PATH = SOURCE_MODEL_DIR / "priority" / "priority_engine_best_metadata.json"
PACKAGED_RISK_METADATA_PATH = CURRENT_BEST_MODEL_METADATA_DIR / "risk_model_best_metadata.json"
PACKAGED_LEADTIME_METADATA_PATH = CURRENT_BEST_MODEL_METADATA_DIR / "leadtime_model_best_metadata.json"
PACKAGED_PRIORITY_METADATA_PATH = CURRENT_BEST_MODEL_METADATA_DIR / "priority_engine_best_metadata.json"

RISK_MODEL_PATH = RISK_MODEL_DIR / "risk_model_best.joblib"
RISK_METADATA_PATH = RISK_MODEL_DIR / "risk_model_best_metadata.json"
LEADTIME_MODEL_PATH = LEADTIME_MODEL_DIR / "leadtime_model_best.joblib"
LEADTIME_METADATA_PATH = LEADTIME_MODEL_DIR / "leadtime_model_best_metadata.json"
PRIORITY_METADATA_PATH = PRIORITY_MODEL_DIR / "priority_engine_best_metadata.json"

SOURCE_RISK_SCORES_PATH = SOURCE_OUTPUT_DIR / "risk_scores.csv"
SOURCE_LEADTIME_SCORES_PATH = SOURCE_OUTPUT_DIR / "leadtime_scores.csv"
SOURCE_PRIORITY_SCORES_PATH = SOURCE_OUTPUT_DIR / "priority_scores.csv"
PACKAGED_SOURCE_RISK_SCORES_PATH = CURRENT_BEST_SOURCE_SCORE_DIR / "risk_scores.csv"
PACKAGED_SOURCE_LEADTIME_SCORES_PATH = CURRENT_BEST_SOURCE_SCORE_DIR / "leadtime_scores.csv"
PACKAGED_SOURCE_PRIORITY_SCORES_PATH = CURRENT_BEST_SOURCE_SCORE_DIR / "priority_scores.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
ANOMALY_SPLIT_COLUMN = "split_time_based"
RISK_SPLIT_COLUMN = "split_event_regime_based"
RANDOM_STATE = 42

ANOMALY_THRESHOLD_QUANTILE = 0.99
ANOMALY_WEIGHTS = {"mahalanobis": 0.53, "iforest": 0.47}
ANOMALY_POLICY_NAME = "iforest_ge_0p90_and_mahalanobis_ge_1p00"
ANOMALY_IFOREST_POLICY_THRESHOLD = 0.90
ANOMALY_MAHALANOBIS_POLICY_THRESHOLD = 1.00
CRITICALITY_THRESHOLD = 5
PRIORITY_TARGET_FALSE_ALARM = 0.20
EXCLUDED_EXPERIMENT_PREFIXES = ("raw" + "_ae_", "self" + "_baseline_")
EXCLUDED_EXPERIMENT_MARKERS = ("raw" + "_ae", "self" + "_baseline")

# Actual M1 current-best risk output applies high and critical at 0.92.
# Because risk level assignment checks critical first, the active M1 output has
# low/medium/critical rows and no high rows.
RISK_BASE_THRESHOLDS = {"medium": 0.22, "high": 0.92, "critical": 0.92}
LEADTIME_LABELS = ["0-24h", "1-3d", "3-7d"]
LEADTIME_EXPECTED_HOURS = {"0-24h": 12.0, "1-3d": 48.0, "3-7d": 120.0}

PRIORITY_WEIGHT_SCENARIOS = {
    "baseline_best": {"risk": 0.55, "leadtime": 0.30, "context": 0.15},
    "risk_heavy": {"risk": 0.70, "leadtime": 0.20, "context": 0.10},
    "leadtime_heavy": {"risk": 0.45, "leadtime": 0.40, "context": 0.15},
    "balanced": {"risk": 0.50, "leadtime": 0.30, "context": 0.20},
}

AGENT_OUTPUT_COLUMNS = [
    "manufacturer",
    "substation_id",
    "window_start",
    "window_end",
    "configuration_type",
    "label",
    "fault_label",
    "fault_event_id",
    "anomaly_ensemble_score",
    "anomaly_policy_score",
    "iforest_score_ratio",
    "mahalanobis_score_ratio",
    "anomaly_consensus_count",
    "anomaly_criticality",
    "anomaly_event_label",
    "anomaly_evidence_event_label",
    "anomaly_evidence_source",
    "risk_probability",
    "risk_score",
    "risk_level_calibrated",
    "predicted_lead_time_bucket",
    "leadtime_urgency_score",
    "current_best_priority_score",
    "current_best_priority_level",
    "priority_score",
    "priority_level",
    "priority_source",
    "priority_high_label",
    "m1_specialist_priority_score",
    "m1_specialist_priority_level",
    "m1_hybrid_priority_score",
    "m1_hybrid_priority_level",
    "m1_priority_agreement",
    "m1_specialist_fault_probability",
    "m1_specialist_task_probability",
    "m1_specialist_activity_probability",
    "m1_specialist_pre_event_probability",
    "m1_specialist_primary_state",
    "m1_specialist_secondary_tags",
    "m1_specialist_fault_group",
    "m1_specialist_group_weight",
    "m1_specialist_gate_review_required",
    "m1_specialist_gate_review_reasons",
    "shadow_priority_score",
    "priority_policy_agreement",
    "operational_label",
    "primary_state",
    "review_required",
    "review_reasons",
    "trust_level",
    "first_crossing_time",
    "stable_crossing_time",
    "stable_crossing_lead_hours",
    "why_reason",
    "recommended_action",
]


def ensure_dirs() -> None:
    for path in [
        INTERIM_DIR,
        PROCESSED_DIR,
        OUTPUT_DIR,
        REPORT_DIR,
        RETRAIN_LOG_DIR,
        OUTPUT_DIR / "agent",
        ANOMALY_MODEL_DIR,
        RISK_MODEL_DIR,
        LEADTIME_MODEL_DIR,
        PRIORITY_MODEL_DIR,
        M1_SPECIALIST_MODEL_DIR,
        CURRENT_BEST_ARTIFACT_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def filter_agent_columns(columns: list[str]) -> list[str]:
    """Remove optional experiment fields that should not be part of the agent contract."""
    return [c for c in columns if not c.startswith(EXCLUDED_EXPERIMENT_PREFIXES)]
