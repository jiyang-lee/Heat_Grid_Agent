from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .common import read_json, write_json


def _run_timestamp() -> str:
    if os.environ.get("THIRD_MODEL_REFRESH_RUN_TIMESTAMP") == "1":
        return datetime.now(timezone.utc).isoformat()
    if config.PIPELINE_RUN_METADATA_PATH.exists():
        try:
            previous = read_json(config.PIPELINE_RUN_METADATA_PATH).get("generated_at_utc")
            if previous:
                return str(previous)
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "(empty)"
    data = frame.copy().fillna("")
    columns = [str(c) for c in data.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in data.iterrows():
        values = [str(row[c]).replace("|", "\\|") for c in data.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _binary_metrics(y_true: pd.Series, y_score: pd.Series, threshold: float) -> dict[str, object]:
    y_pred = y_score.ge(threshold).astype(int)
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    fpr = fp / max(1, fp + tn)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": fpr,
    }


def _has_keys(frame: pd.DataFrame) -> bool:
    return all(column in frame.columns for column in config.KEY_COLUMNS)


def _counts_text(frame: pd.DataFrame, column: str) -> str:
    if column not in frame.columns or frame.empty:
        return ""
    counts = frame[column].value_counts(dropna=False).head(8)
    return "; ".join(f"{key}={int(value)}" for key, value in counts.items())


def _compare_key_coverage(
    source_name: str,
    source: pd.DataFrame,
    target_name: str,
    target: pd.DataFrame,
) -> tuple[dict[str, object], pd.DataFrame]:
    source = source.copy()
    target = target.copy()
    if not _has_keys(source) or not _has_keys(target):
        return (
            {
                "source_stage": source_name,
                "target_stage": target_name,
                "source_rows": int(len(source)),
                "target_rows": int(len(target)),
                "source_duplicate_keys": "",
                "target_duplicate_keys": "",
                "missing_from_target": "",
                "missing_pre_fault": "",
                "missing_normal": "",
                "missing_label_distribution": "",
                "missing_split_distribution": "",
            },
            pd.DataFrame(),
        )

    target_keys = target[config.KEY_COLUMNS].drop_duplicates()
    merged = source.merge(target_keys, on=config.KEY_COLUMNS, how="left", indicator=True)
    missing = merged.loc[merged["_merge"].eq("left_only")].drop(columns=["_merge"])
    missing_pre_fault = int(missing["label"].eq("pre_fault").sum()) if "label" in missing.columns else ""
    missing_normal = int(missing["label"].eq("normal").sum()) if "label" in missing.columns else ""
    return (
        {
            "source_stage": source_name,
            "target_stage": target_name,
            "source_rows": int(len(source)),
            "target_rows": int(len(target)),
            "source_duplicate_keys": int(source.duplicated(config.KEY_COLUMNS).sum()),
            "target_duplicate_keys": int(target.duplicated(config.KEY_COLUMNS).sum()),
            "missing_from_target": int(len(missing)),
            "missing_pre_fault": missing_pre_fault,
            "missing_normal": missing_normal,
            "missing_label_distribution": _counts_text(missing, "label"),
            "missing_split_distribution": _counts_text(missing, config.ANOMALY_SPLIT_COLUMN),
        },
        missing,
    )


def row_reconciliation() -> pd.DataFrame:
    tables: dict[str, pd.DataFrame] = {}
    paths = {
        "canonical_windows": config.TRAINABLE_WINDOWS_PATH,
        "priority_scores": config.PRIORITY_SCORES_PATH,
        "merged_scores": config.MERGED_SCORES_PATH,
        "agent_card": config.AGENT_CARD_PATH,
    }
    for name, path in paths.items():
        if path.exists():
            tables[name] = pd.read_csv(path)

    comparisons = [
        ("canonical_windows", "priority_scores"),
        ("canonical_windows", "agent_card"),
        ("priority_scores", "merged_scores"),
        ("priority_scores", "agent_card"),
        ("agent_card", "canonical_windows"),
    ]
    rows: list[dict[str, object]] = []
    missing_agent = pd.DataFrame()
    for source_name, target_name in comparisons:
        if source_name not in tables or target_name not in tables:
            continue
        row, missing = _compare_key_coverage(source_name, tables[source_name], target_name, tables[target_name])
        rows.append(row)
        if source_name == "canonical_windows" and target_name == "agent_card":
            missing_agent = missing

    table = pd.DataFrame(rows)
    table.to_csv(config.ROW_RECONCILIATION_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    missing_agent.to_csv(config.MISSING_AGENT_WINDOWS_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    return table


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _csv_file_metadata(name: str, path: Path) -> dict[str, object]:
    path_obj = Path(path)
    if not path_obj.exists():
        return {"name": name, "path": config.path_label(path_obj), "exists": False}
    frame = pd.read_csv(path_obj)
    stat = path_obj.stat()
    return {
        "name": name,
        "path": config.path_label(path_obj),
        "exists": True,
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "size_bytes": int(stat.st_size),
        "sha256": _sha256(path_obj),
    }


def _artifact_file_metadata(name: str, path: Path) -> dict[str, object]:
    path_obj = Path(path)
    if not path_obj.exists():
        return {"name": name, "path": config.path_label(path_obj), "exists": False}
    stat = path_obj.stat()
    return {
        "name": name,
        "path": config.path_label(path_obj),
        "exists": True,
        "size_bytes": int(stat.st_size),
        "sha256": _sha256(path_obj),
    }


def _scan_artifacts(root: Path) -> list[dict[str, object]]:
    if not root.exists():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if any(part in {".venv", "__pycache__"} for part in path.parts) or path.suffix == ".pyc":
            continue
        if path.is_file():
            rows.append(_artifact_file_metadata(str(path.relative_to(config.PROJECT_ROOT)), path))
    return rows


def pipeline_run_metadata() -> dict[str, object]:
    files = {
        "trainable_windows": config.TRAINABLE_WINDOWS_PATH,
        "anomaly_scores": config.ANOMALY_SCORES_PATH,
        "risk_scores": config.RISK_SCORES_PATH,
        "leadtime_scores": config.LEADTIME_SCORES_PATH,
        "priority_scores": config.PRIORITY_SCORES_PATH,
        "merged_model_scores": config.MERGED_SCORES_PATH,
        "agent_priority_card": config.AGENT_CARD_PATH,
        "agent_card_column_dictionary_ko": config.AGENT_CARD_COLUMN_DICTIONARY_PATH,
        "agent_card_column_groups_ko": config.AGENT_CARD_COLUMN_GROUPS_PATH,
        "m1_specialist_gate_scores": config.M1_SPECIALIST_GATE_SCORES_PATH,
        "m1_specialist_scores": config.M1_SPECIALIST_SCORES_PATH,
        "row_reconciliation": config.ROW_RECONCILIATION_PATH,
        "missing_agent_windows": config.MISSING_AGENT_WINDOWS_PATH,
        "ablation_summary": config.ABLATION_SUMMARY_PATH,
        "threshold_sweep": config.THRESHOLD_SWEEP_PATH,
        "priority_weight_sensitivity": config.PRIORITY_SENSITIVITY_PATH,
        "hard_normal_audit": config.HARD_NORMAL_AUDIT_PATH,
        "anomaly_criticality_threshold_sweep": config.ANOMALY_CRITICALITY_SWEEP_PATH,
        "anomaly_if_mahalanobis_policy_grid": config.ANOMALY_IF_MAHALANOBIS_GRID_PATH,
        "hybrid_weight_sweep": config.HYBRID_WEIGHT_SWEEP_PATH,
        "hybrid_weight_selection_summary": config.HYBRID_WEIGHT_SELECTION_SUMMARY_PATH,
        "hybrid_065_vs_072_metric_delta": config.HYBRID_065_VS_072_METRIC_DELTA_PATH,
        "hybrid_065_vs_072_level_transition": config.HYBRID_065_VS_072_LEVEL_TRANSITION_PATH,
        "hybrid_065_vs_072_changed_rows": config.HYBRID_065_VS_072_CHANGED_ROWS_PATH,
        "priority_engine_component_summary": config.PRIORITY_COMPONENT_SUMMARY_PATH,
        "row_flow_summary": config.ROW_FLOW_SUMMARY_PATH,
        "key_coverage_by_artifact": config.KEY_COVERAGE_BY_ARTIFACT_PATH,
        "risk_level_actual_summary": config.RISK_LEVEL_ACTUAL_SUMMARY_PATH,
        "risk_threshold_actual_values": config.RISK_THRESHOLD_ACTUAL_VALUES_PATH,
        "m1_gate_threshold_sweep": config.M1_GATE_THRESHOLD_SWEEP_PATH,
        "m1_gate_selected_threshold_summary": config.M1_GATE_SELECTED_THRESHOLD_SUMMARY_PATH,
        "m1_gate_threshold_reference": config.M1_GATE_THRESHOLD_REFERENCE_PATH,
        "m1_specialist_priority_weight_ablation": config.M1_SPECIALIST_PRIORITY_WEIGHT_ABLATION_PATH,
        "m1_specialist_priority_weight_grid": config.M1_SPECIALIST_PRIORITY_WEIGHT_GRID_PATH,
        "fault_group_weight_summary": config.FAULT_GROUP_WEIGHT_SUMMARY_PATH,
        "level_calibration_fpr_cap_sweep": config.LEVEL_CALIBRATION_FPR_CAP_SWEEP_PATH,
        "hybrid_selected_weight_comparison": config.HYBRID_SELECTED_WEIGHT_COMPARISON_PATH,
    }
    model_files = {
        "anomaly_standard_scaler": config.ANOMALY_SCALER_PATH,
        "anomaly_isolation_forest": config.IFOREST_MODEL_PATH,
        "anomaly_mahalanobis": config.MAHALANOBIS_MODEL_PATH,
        "anomaly_metadata": config.ANOMALY_METADATA_PATH,
        "risk_model_best": config.RISK_MODEL_PATH,
        "risk_model_best_metadata": config.RISK_METADATA_PATH,
        "leadtime_model_best": config.LEADTIME_MODEL_PATH,
        "leadtime_model_best_metadata": config.LEADTIME_METADATA_PATH,
        "priority_engine_best_metadata": config.PRIORITY_METADATA_PATH,
        "m1_fault_gate": config.M1_SPECIALIST_MODEL_DIR / "m1_fault_gate_rf_depth3.joblib",
        "m1_task_gate": config.M1_SPECIALIST_MODEL_DIR / "m1_task_gate_rf_depth3.joblib",
        "m1_activity_gate": config.M1_SPECIALIST_MODEL_DIR / "m1_activity_gate_rf_depth3.joblib",
        "m1_pre_event_gate": config.M1_SPECIALIST_MODEL_DIR / "m1_fault_pre_event_logistic.joblib",
        "m1_specialist_gate_metadata": config.M1_SPECIALIST_GATE_METADATA_PATH,
    }
    payload = {
        "generated_at_utc": _run_timestamp(),
        "source_best_root": config.path_label(config.SOURCE_BEST_ROOT, "THIRD_MODEL_SOURCE_BEST_ROOT"),
        "source_best_available": config.SOURCE_BEST_ROOT.exists(),
        "files": [_csv_file_metadata(name, path) for name, path in files.items() if Path(path).suffix.lower() == ".csv"],
        "model_files": [_artifact_file_metadata(name, path) for name, path in model_files.items()],
        "supporting_artifacts": _scan_artifacts(config.CURRENT_BEST_ARTIFACT_DIR),
        "compare_files": _scan_artifacts(config.PROJECT_ROOT / "compare"),
        "markdown_reports": {
            "final_validation_report": config.path_label(config.FINAL_VALIDATION_MD_PATH),
            "m1_specialist_report": config.path_label(config.M1_SPECIALIST_REPORT_PATH),
            "agent_card_column_groups": config.path_label(config.AGENT_CARD_COLUMN_GROUPS_MD_PATH),
            "agent_card_value_mapping": config.path_label(config.AGENT_CARD_VALUE_MAPPING_PATH),
        },
    }
    write_json(config.PIPELINE_RUN_METADATA_PATH, payload)
    return payload


def threshold_sweep() -> pd.DataFrame:
    frame = pd.read_csv(config.AGENT_CARD_PATH)
    mask = frame["label"].isin(["normal", "pre_fault"])
    y_true = frame.loc[mask, "label"].eq("pre_fault").astype(int)
    rows: list[dict[str, object]] = []
    targets = {
        "anomaly_policy_score": frame.loc[mask, "anomaly_policy_score"],
        "anomaly_ensemble_score": frame.loc[mask, "anomaly_ensemble_score"],
        "risk_score": frame.loc[mask, "risk_score"],
        "priority_score": frame.loc[mask, "priority_score"] / 100.0,
    }
    for score_name, score in targets.items():
        numeric = pd.to_numeric(score, errors="coerce").fillna(0.0)
        for threshold in np.linspace(0.1, 0.9, 9):
            row = _binary_metrics(y_true, numeric, float(threshold))
            row["score_name"] = score_name
            rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(config.THRESHOLD_SWEEP_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    return table


def ablation_summary() -> pd.DataFrame:
    frame = pd.read_csv(config.AGENT_CARD_PATH)
    y_true = frame["label"].eq("pre_fault").astype(int)
    anomaly_event = pd.to_numeric(frame["anomaly_evidence_event_label"], errors="coerce").fillna(0).astype(int)
    risk_high = frame["risk_level_calibrated"].isin(["high", "critical"]).astype(int)
    priority_high = frame["priority_level"].isin(["high", "urgent"]).astype(int)
    specialist_high = frame["m1_specialist_priority_level"].isin(["high", "urgent"]).astype(int)
    candidates = {
        "official_anomaly_evidence_event": anomaly_event,
        "risk_high_or_critical": risk_high,
        "m1_specialist_high_or_urgent": specialist_high,
        "priority_high_or_urgent": priority_high,
        "anomaly_or_risk_high": (anomaly_event.eq(1) | risk_high.eq(1)).astype(int),
    }
    rows: list[dict[str, object]] = []
    for name, pred in candidates.items():
        tp = int(((y_true == 1) & (pred == 1)).sum())
        fp = int(((y_true == 0) & (pred == 1)).sum())
        fn = int(((y_true == 1) & (pred == 0)).sum())
        tn = int(((y_true == 0) & (pred == 0)).sum())
        rows.append(
            {
                "variant": name,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "precision": tp / max(1, tp + fp),
                "recall": tp / max(1, tp + fn),
                "false_positive_rate": fp / max(1, fp + tn),
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(config.ABLATION_SUMMARY_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    lines = [
        "# Ablation 요약",
        "",
        "이 리포트는 최종 agent contract에 남긴 active 정책만 비교합니다.",
        "",
        _markdown_table(table),
    ]
    config.ABLATION_SUMMARY_MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    return table


def _anomaly_context(frame: pd.DataFrame) -> pd.Series:
    anomaly_event = pd.to_numeric(frame["anomaly_evidence_event_label"], errors="coerce").fillna(0)
    consensus = pd.to_numeric(frame["anomaly_consensus_count"], errors="coerce").fillna(0)
    values = np.select(
        [anomaly_event.ge(1), consensus.ge(2), consensus.eq(1)],
        [0.75, 0.60, 0.30],
        default=0.10,
    )
    return pd.Series(values, index=frame.index, dtype="float64")


def priority_sensitivity() -> pd.DataFrame:
    frame = pd.read_csv(config.AGENT_CARD_PATH)
    sort_columns = ["priority_score", "manufacturer", "substation_id", "window_end"]
    base = frame.sort_values(sort_columns, ascending=[False, True, True, True]).head(10)
    base_keys = set(zip(base["manufacturer"], base["substation_id"], base["window_end"]))
    rows: list[dict[str, object]] = []
    risk = pd.to_numeric(frame["risk_score"], errors="coerce").fillna(
        pd.to_numeric(frame["risk_probability"], errors="coerce").fillna(0.0)
    )
    lead = pd.to_numeric(frame["leadtime_urgency_score"], errors="coerce").fillna(0.0)
    context = _anomaly_context(frame)
    for name, weights in config.PRIORITY_WEIGHT_SCENARIOS.items():
        score = 100 * (weights["risk"] * risk + weights["leadtime"] * lead + weights["context"] * context)
        top = frame.assign(_scenario_score=score).sort_values(
            ["_scenario_score", "manufacturer", "substation_id", "window_end"],
            ascending=[False, True, True, True],
        ).head(10)
        keys = set(zip(top["manufacturer"], top["substation_id"], top["window_end"]))
        rows.append(
            {
                "scenario": name,
                "w_risk": weights["risk"],
                "w_leadtime": weights["leadtime"],
                "w_context": weights["context"],
                "top10_overlap_rate": len(base_keys & keys) / max(1, len(base_keys)),
                "review_required_in_top10": int(top["review_required"].astype(bool).sum()),
                "mean_top10_score": float(top["_scenario_score"].mean()),
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(config.PRIORITY_SENSITIVITY_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    return table


def hard_normal_audit() -> pd.DataFrame:
    frame = pd.read_csv(config.AGENT_CARD_PATH)
    mask = frame["review_reasons"].fillna("").str.contains("hard_normal_review")
    audit = frame.loc[mask].copy()
    keep = [
        "manufacturer",
        "substation_id",
        "window_start",
        "window_end",
        "risk_score",
        "anomaly_policy_score",
        "anomaly_ensemble_score",
        "anomaly_criticality",
        "anomaly_event_label",
        "anomaly_evidence_event_label",
        "anomaly_evidence_source",
        "review_reasons",
        "why_reason",
    ]
    audit = audit[[c for c in keep if c in audit.columns]]
    audit.to_csv(config.HARD_NORMAL_AUDIT_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    return audit


def write_final_validation_report() -> None:
    reconciliation = pd.read_csv(config.ROW_RECONCILIATION_PATH)
    metadata = read_json(config.PIPELINE_RUN_METADATA_PATH)
    threshold = pd.read_csv(config.THRESHOLD_SWEEP_PATH)
    ablation = pd.read_csv(config.ABLATION_SUMMARY_PATH)
    sensitivity = pd.read_csv(config.PRIORITY_SENSITIVITY_PATH)
    hard_normal = pd.read_csv(config.HARD_NORMAL_AUDIT_PATH)
    supporting_count = len(metadata.get("supporting_artifacts", []))
    compare_count = len(metadata.get("compare_files", []))
    lines = [
        "# 최종 검증 보고서",
        "",
        "## 현재 활성 계약",
        "- 공식 agent `priority_score`와 `priority_level`은 M1 hybrid priority 산출물이다.",
        "- 최종 agent card인 `output/agent_priority_card.csv`와 `output/agent/m1_agent_priority_card.csv`는 1226 rows / 55 columns다.",
        "- `output/agent/m1_specialist_parallel_agent_card.csv`는 1252 rows / 29 columns의 M1 단독 병렬 근거 card이며, 최종 hybrid agent 계약이 아니다.",
        "- M1 hybrid priority = 0.65 * current-best priority + 0.35 * M1 specialist priority.",
        "- Hybrid 0.65/0.35는 모든 metric의 절대 최적값이 아니라 운영 선택점이다. 0.72/0.28 및 0.90/0.10 비교는 threshold/weight 근거 notebook에서 확인한다.",
        "- Active anomaly policy는 IsolationForest ratio >= 0.90 AND Mahalanobis ratio >= 1.00이며, criticality 지속성을 함께 본다.",
        "- 실제 M1 current-best risk level 기준은 medium=0.22, high=0.92, critical=0.92다. high와 critical cutoff가 같으므로 현재 M1 output에는 low/medium/critical row만 존재한다.",
        "- 원래 current-best priority는 `current_best_priority_score`, `current_best_priority_level`로 보존한다.",
        "- `m1_specialist_*` 필드는 active 근거 필드이며 risk/leadtime의 단독 대체 모델이 아니다.",
        "- `m1_specialist_group_weight`는 현재 fault-label-derived group과 강하게 연결되어 있어 live inference 적용 시 별도 검토가 필요하다.",
        "- M1 gate threshold는 독립 알람 최적값이 아니라 근거 threshold다. task/activity gate는 native label이 없어 독립 성능 claim으로 쓰지 않는다.",
        "",
        "## 출처 추적",
        "- [current best] risk, leadtime, priority body",
        "- [current best models] 추적성을 위해 risk_model_best.joblib, leadtime_model_best.joblib 포함",
        "- [current best supporting artifacts] metric, threshold, feature contract, score source, experiment trace는 artifacts/current_best 아래 보존",
        "- [comparison notebooks] 성능 비교와 threshold/weight 근거 notebook은 compare 아래 보존",
        "- [M1 anomaly] IsolationForest ratio >= 0.90 AND Mahalanobis ratio >= 1.00 active policy",
        "- [M1 specialist] fault/task/activity/pre-event gate, fault group, review flag",
        "- [agent card contract] output/agent 아래 컬럼 사전, value mapping, 컬럼 분류표 포함",
        "- [report defense audit] docs/08_MODEL_REPORT_DEFENSE_AUDIT.md에 보고 방어 체크리스트와 재실험/문서 보완 구분 포함",
        "",
        "## 실행 Metadata",
        f"- generated_at_utc: {metadata.get('generated_at_utc')}",
        f"- source_best_root: {metadata.get('source_best_root')}",
        f"- metadata_file: {config.path_label(config.PIPELINE_RUN_METADATA_PATH)}",
        f"- supporting_artifact_count: {supporting_count}",
        f"- compare_file_count: {compare_count}",
        "",
        "## Row 정합성",
        _markdown_table(reconciliation),
        "",
        "## Threshold Sweep 예시",
        _markdown_table(threshold.head(12)),
        "",
        "## Active Policy Ablation",
        _markdown_table(ablation),
        "",
        "## Priority 민감도",
        _markdown_table(sensitivity),
        "",
        f"## Hard Normal Review 건수\n\n{len(hard_normal)}",
    ]
    config.FINAL_VALIDATION_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def run_all_validations() -> None:
    row_reconciliation()
    threshold_sweep()
    ablation_summary()
    priority_sensitivity()
    hard_normal_audit()
    pipeline_run_metadata()
    write_final_validation_report()
