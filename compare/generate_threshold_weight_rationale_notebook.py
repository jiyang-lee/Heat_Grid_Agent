from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf


OUT = Path(__file__).resolve().parent / "m1_threshold_weight_rationale_report.ipynb"


def md(text: str):
    return nbf.v4.new_markdown_cell(dedent(text).strip())


def code(text: str):
    return nbf.v4.new_code_cell(dedent(text).strip())


nb = nbf.v4.new_notebook()
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "pygments_lexer": "ipython3"},
}

nb["cells"] = [
    md(
        """
        # Threshold / Weight / Priority Engine 근거 보고서

        이 노트북은 현재 `agent/mlmodel` 저장소에서 사용한 threshold와 weight가 왜 그렇게 설정됐는지 설명하는 보고용 근거 문서다.

        핵심 결론:

        - anomaly threshold는 정상 train 분포의 q99를 기준으로 ratio화했고, 단독 알람이 아니라 evidence로 남겼다.
        - risk threshold는 event recall을 유지하면서 false positive를 줄이는 운영 trade-off에서 선택됐다.
        - leadtime은 시간 근접성 참고 신호다. exact bucket 성능이 risk보다 약하므로 priority에서 보조 weight로 둔다.
        - priority engine에서 risk 비중이 가장 큰 이유는 risk가 supervised event probability이고, holdout에서 FPR을 낮게 유지하면서 event recall을 가장 안정적으로 확보했기 때문이다.
        - M1 hybrid `0.65 / 0.35`는 current-best baseline을 주축으로 유지하면서 M1 specialist 근거를 의미 있게 반영하는 conservative operating point다. 수학적으로 유일한 최적점이라고 주장하지 않고, 비교 실험상 운영 안정성과 설명력을 같이 만족하는 지점으로 해석한다.
        - M1 gate `0.50 / 0.60`은 standalone alarm 최적값이 아니라 priority에 투입되는 evidence threshold다.
        - 실제 M1 risk output의 applied threshold는 `0.22 / 0.92 / 0.92`이며, `0.44`는 현재 산출물 기준 active threshold가 아니다.
        """
    ),
    md(
        """
        ## 1. 데이터 로드와 파생 실험 생성

        아래 셀은 저장소 내부 파일만 사용한다. notebook을 다른 위치에서 열어도 `M1_SPECIALIST_REPO_ROOT` 환경변수나 현재 작업 경로 기준으로 저장소 root를 찾는다.

        생성되는 파생 CSV:

        - `output/reports/anomaly_criticality_threshold_sweep.csv`
        - `output/reports/anomaly_if_mahalanobis_policy_grid.csv`
        - `output/reports/hybrid_weight_sweep.csv`
        - `output/reports/priority_engine_component_summary.csv`
        - `output/reports/row_flow_summary.csv`
        - `output/reports/key_coverage_by_artifact.csv`
        - `output/agent/agent_card_column_groups_ko.csv`
        - `output/reports/risk_level_actual_summary.csv`
        - `output/reports/risk_threshold_actual_values.csv`
        - `output/reports/m1_gate_threshold_sweep.csv`
        - `output/reports/m1_gate_selected_threshold_summary.csv`
        - `output/reports/m1_gate_threshold_reference.csv`
        - `output/reports/m1_specialist_priority_weight_ablation.csv`
        - `output/reports/m1_specialist_priority_weight_grid.csv`
        - `output/reports/fault_group_weight_summary.csv`
        - `output/reports/level_calibration_fpr_cap_sweep.csv`
        - `output/reports/hybrid_selected_weight_comparison.csv`
        - `output/reports/hybrid_065_vs_072_metric_delta.csv`
        - `output/reports/hybrid_065_vs_072_level_transition.csv`
        - `output/reports/hybrid_065_vs_072_changed_rows.csv`
        """
    ),
    code(
        r"""
        import os
        import json
        from pathlib import Path

        import numpy as np
        import pandas as pd
        from IPython.display import display, Markdown
        import plotly.express as px
        import plotly.graph_objects as go
        import plotly.io as pio
        from plotly.subplots import make_subplots

        pio.renderers.default = "notebook_connected"

        def find_repo_root() -> Path:
            candidates = []
            env_root = os.environ.get("M1_SPECIALIST_REPO_ROOT")
            if env_root:
                candidates.append(Path(env_root))
            cwd = Path.cwd()
            candidates.extend([cwd, *cwd.parents])
            for candidate in candidates:
                if (
                    (candidate / "output/m1_specialist_scores.csv").exists()
                    and (candidate / "artifacts/current_best").exists()
                ):
                    return candidate
            raise FileNotFoundError("M1 specialist repository root not found. Set M1_SPECIALIST_REPO_ROOT.")

        PKG = find_repo_root()
        ART = PKG / "artifacts" / "current_best"
        REPORT = PKG / "output" / "reports"
        REPORT.mkdir(parents=True, exist_ok=True)

        COLORS = {
            "blue": "#2563EB",
            "green": "#16A34A",
            "red": "#DC2626",
            "orange": "#F97316",
            "teal": "#0891B2",
            "purple": "#7C3AED",
            "gray": "#64748B",
            "slate": "#334155",
        }

        def read_csv(rel: str) -> pd.DataFrame:
            path = PKG / rel
            if not path.exists():
                raise FileNotFoundError(path)
            return pd.read_csv(path)

        def read_art_csv(rel: str) -> pd.DataFrame:
            path = ART / rel
            if not path.exists():
                raise FileNotFoundError(path)
            return pd.read_csv(path)

        def read_json_file(path: Path) -> dict:
            return json.loads(path.read_text(encoding="utf-8"))

        anomaly = read_csv("output/anomaly_scores.csv")
        anomaly_metrics = read_csv("output/anomaly_metrics.csv")
        trainable_windows = read_csv("data/processed/trainable_windows.csv")
        m1_scores = read_csv("output/m1_specialist_scores.csv")
        m1_compare = read_csv("output/reports/m1_specialist_vs_current_best_comparison.csv")
        active_ablation = read_csv("output/reports/ablation_summary.csv")
        row_reconciliation = read_csv("output/reports/row_reconciliation.csv")
        missing_agent_windows = read_csv("output/reports/missing_agent_windows.csv")
        agent_column_groups = read_csv("output/agent/agent_card_column_groups_ko.csv")
        threshold_sweep = read_csv("output/reports/threshold_sweep.csv")
        priority_weight_sensitivity = read_csv("output/reports/priority_weight_sensitivity.csv")
        risk_scores = read_csv("output/risk_scores.csv")
        priority_scores = read_csv("output/priority_scores.csv")
        source_current_best_scores = read_art_csv("source_score_outputs/risk_scores.csv")

        risk_threshold = read_art_csv("reports/risk/risk_threshold_selection.csv")
        risk_group_threshold = read_art_csv("reports/risk/risk_group_threshold_selection.csv")
        risk_metrics = read_art_csv("reports/risk/risk_metrics.csv")
        risk_event_metrics = read_art_csv("reports/risk/risk_event_metrics.csv")
        leadtime_metrics = read_art_csv("reports/leadtime/leadtime_metrics.csv")
        leadtime_confusion = read_art_csv("reports/leadtime/leadtime_confusion_matrix.csv")
        leadtime_ablation = read_art_csv("reports/leadtime/leadtime_ablation_metrics.csv")
        best_pipeline = read_art_csv("reports/best_pipeline_comparison.csv")
        operational_policy = read_art_csv("reports/operational/operational_policy_comparison.csv")
        priority_lgbm_class = read_art_csv("experiment_traces/priority_compare/priority_lgbm_vs_rule_classification_metrics.csv")
        priority_lgbm_topk = read_art_csv("experiment_traces/priority_compare/priority_lgbm_vs_rule_topk_metrics.csv")

        anomaly_meta = read_json_file(PKG / "models/anomaly/anomaly_metadata.json")
        priority_meta = read_json_file(PKG / "models/priority/priority_engine_best_metadata.json")
        m1_meta = read_json_file(PKG / "output/reports/m1_specialist_metadata.json")
        window_import_meta = read_json_file(PKG / "data/processed/window_import_metadata.json")
        source_retrain_meta = read_json_file(PKG / "output/reports/source_retrain_metadata.json") if (PKG / "output/reports/source_retrain_metadata.json").exists() else {}
        m1_source_retrain_meta = read_json_file(PKG / "output/reports/m1_source_retrain_metadata.json") if (PKG / "output/reports/m1_source_retrain_metadata.json").exists() else {}

        KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]

        def tidy(fig, height=430):
            fig.update_layout(
                template="plotly_white",
                height=height,
                title_x=0.02,
                font=dict(size=13),
                legend_title="",
                margin=dict(l=40, r=25, t=70, b=70),
            )
            return fig

        def binary_metrics(part: pd.DataFrame, pred: pd.Series) -> dict:
            y = part["label"].eq("pre_fault")
            pred = pred.reindex(part.index).fillna(False).astype(bool)
            tp = int((y & pred).sum())
            fp = int((~y & pred).sum())
            fn = int((y & ~pred).sum())
            tn = int((~y & ~pred).sum())
            precision = tp / max(1, tp + fp)
            recall = tp / max(1, tp + fn)
            fpr = fp / max(1, fp + tn)
            f1 = 2 * precision * recall / max(1e-12, precision + recall)
            event = part.loc[part["label"].eq("pre_fault") & part["fault_event_id"].notna()].copy()
            total_events = int(event["fault_event_id"].nunique())
            detected_events = 0
            if total_events:
                detected_events = int(
                    event.assign(_pred=pred.loc[event.index].astype(int))
                    .groupby("fault_event_id")["_pred"]
                    .max()
                    .sum()
                )
            return {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "false_positive_rate": fpr,
                "fault_events": total_events,
                "detected_fault_events": detected_events,
                "fault_event_recall": detected_events / max(1, total_events),
            }

        def recompute_criticality(frame: pd.DataFrame) -> pd.Series:
            work = frame[[*KEY_COLUMNS, "anomaly_policy_score"]].copy()
            work["window_end_dt"] = pd.to_datetime(work["window_end"], errors="coerce")
            work["_original_index"] = work.index
            work = work.sort_values(["manufacturer", "substation_id", "window_end_dt", "window_start"])
            values = pd.Series(0, index=work.index, dtype="int64")
            for _, group in work.groupby(["manufacturer", "substation_id"], dropna=False, sort=False):
                count = 0
                for idx, row in group.iterrows():
                    if float(row["anomaly_policy_score"]) >= 1.0:
                        count += 1
                    else:
                        count = max(0, count - 1)
                    values.loc[idx] = count
            values.index = work["_original_index"]
            return values.reindex(frame.index)

        anomaly_counter = recompute_criticality(anomaly)
        criticality_rows = []
        for criticality_threshold in range(1, 13):
            pred_all = anomaly_counter.ge(criticality_threshold)
            for split, part in anomaly.groupby("split_time_based", dropna=False):
                metrics = binary_metrics(part, pred_all.loc[part.index])
                metrics.update({"split": split, "criticality_threshold": criticality_threshold})
                criticality_rows.append(metrics)
        criticality_sweep = pd.DataFrame(criticality_rows)
        criticality_sweep.to_csv(REPORT / "anomaly_criticality_threshold_sweep.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        anomaly_policy_grid_rows = []
        for if_threshold in np.round(np.arange(0.75, 1.201, 0.05), 2):
            for mahalanobis_threshold in np.round(np.arange(0.80, 1.301, 0.05), 2):
                pred_all = (
                    pd.to_numeric(anomaly["iforest_score_ratio"], errors="coerce").fillna(0.0).ge(if_threshold)
                    & pd.to_numeric(anomaly["mahalanobis_score_ratio"], errors="coerce").fillna(0.0).ge(mahalanobis_threshold)
                )
                for split, part in anomaly.groupby("split_time_based", dropna=False):
                    metrics = binary_metrics(part, pred_all.loc[part.index])
                    metrics.update(
                        {
                            "split": split,
                            "iforest_ratio_threshold": if_threshold,
                            "mahalanobis_ratio_threshold": mahalanobis_threshold,
                        }
                    )
                    anomaly_policy_grid_rows.append(metrics)
        anomaly_policy_grid = pd.DataFrame(anomaly_policy_grid_rows)
        anomaly_policy_grid.to_csv(REPORT / "anomaly_if_mahalanobis_policy_grid.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        coverage_rows = []
        for artifact_name, frame in [
            ("risk_scores", risk_scores),
            ("leadtime_scores", read_csv("output/leadtime_scores.csv")),
            ("priority_scores", priority_scores),
            ("m1_specialist_scores", m1_scores),
            ("priority_cards", read_csv("output/agent_priority_card.csv")),
        ]:
            merged = trainable_windows.merge(
                frame[KEY_COLUMNS].drop_duplicates(KEY_COLUMNS),
                on=KEY_COLUMNS,
                how="left",
                indicator=True,
            )
            missing = merged.loc[merged["_merge"].eq("left_only")].copy()
            coverage_rows.append(
                {
                    "artifact": artifact_name,
                    "source_rows": int(len(trainable_windows)),
                    "target_rows": int(len(frame)),
                    "missing_from_target": int(len(missing)),
                    "missing_pre_fault": int(missing["label"].eq("pre_fault").sum()),
                    "missing_normal": int(missing["label"].eq("normal").sum()),
                    "missing_split_distribution": "; ".join(
                        f"{k}={v}" for k, v in missing["split_time_based"].value_counts(dropna=False).items()
                    ),
                    "missing_fault_events": int(
                        missing.loc[missing["label"].eq("pre_fault"), "fault_event_id"].dropna().nunique()
                    ),
                }
            )
        key_coverage_by_artifact = pd.DataFrame(coverage_rows)
        key_coverage_by_artifact.to_csv(REPORT / "key_coverage_by_artifact.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        risk_threshold_columns = [
            "risk_threshold_medium_applied",
            "risk_threshold_high_applied",
            "risk_threshold_critical_applied",
        ]
        risk_threshold_actual_values = risk_scores[risk_threshold_columns].drop_duplicates().sort_values(risk_threshold_columns)
        risk_threshold_actual_values.to_csv(REPORT / "risk_threshold_actual_values.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")
        risk_level_actual_summary = (
            risk_scores.groupby("risk_level_calibrated", dropna=False)
            .agg(
                rows=("risk_score", "size"),
                min_risk_score=("risk_score", "min"),
                max_risk_score=("risk_score", "max"),
                mean_risk_score=("risk_score", "mean"),
                pre_fault_rows=("label", lambda s: int((s == "pre_fault").sum())),
                normal_rows=("label", lambda s: int((s == "normal").sum())),
            )
            .reset_index()
        )
        for column in risk_threshold_columns:
            risk_level_actual_summary[column] = float(pd.to_numeric(risk_scores[column], errors="coerce").dropna().iloc[0])
        risk_level_actual_summary.to_csv(REPORT / "risk_level_actual_summary.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        gate_scores = read_csv("output/m1_specialist_gate_scores.csv")
        gate_context = trainable_windows[
            [
                *KEY_COLUMNS,
                "split_time_based",
                "maintenance_related",
                "disturbance_count",
                "normal_event_related",
                "use_for_supervised_training",
            ]
        ].drop_duplicates(KEY_COLUMNS)
        gate_eval = gate_scores.merge(gate_context, on=KEY_COLUMNS, how="left", validate="one_to_one")
        gate_rows = []
        gate_defs = [
            ("fault_gate", "m1_specialist_fault_probability", "pre_fault_proxy"),
            ("pre_event_gate", "m1_specialist_pre_event_probability", "pre_fault_proxy"),
            ("task_gate", "m1_specialist_task_probability", "task_proxy_maintenance_or_disturbance"),
            ("activity_gate", "m1_specialist_activity_probability", "activity_native_label_unavailable"),
        ]
        for gate, prob_col, target_definition in gate_defs:
            for threshold in np.round(np.arange(0.30, 0.801, 0.05), 2):
                for split, part in gate_eval[gate_eval["label"].notna()].groupby("split_time_based", dropna=False):
                    if target_definition == "task_proxy_maintenance_or_disturbance":
                        y_true = (
                            part["maintenance_related"].fillna(False).astype(bool)
                            | pd.to_numeric(part["disturbance_count"], errors="coerce").fillna(0).gt(0)
                        )
                    else:
                        y_true = part["label"].eq("pre_fault")
                    pred = pd.to_numeric(part[prob_col], errors="coerce").fillna(0.0).ge(threshold)
                    tp = int((y_true & pred).sum())
                    fp = int((~y_true & pred).sum())
                    fn = int((y_true & ~pred).sum())
                    tn = int((~y_true & ~pred).sum())
                    precision = tp / max(1, tp + fp)
                    recall = tp / max(1, tp + fn)
                    fpr = fp / max(1, fp + tn)
                    f1 = 2 * precision * recall / max(1e-12, precision + recall)
                    specificity = tn / max(1, fp + tn)
                    gate_rows.append(
                        {
                            "gate": gate,
                            "probability_column": prob_col,
                            "target_definition": target_definition,
                            "threshold": threshold,
                            "split": split,
                            "tp": tp,
                            "fp": fp,
                            "fn": fn,
                            "tn": tn,
                            "precision": precision,
                            "recall": recall,
                            "f1": f1,
                            "false_positive_rate": fpr,
                            "balanced_accuracy": (recall + specificity) / 2,
                            "positive_rate": float(pred.mean()),
                            "target_positive_count": int(y_true.sum()),
                            "native_label_available": target_definition != "activity_native_label_unavailable",
                        }
                    )
        m1_gate_threshold_sweep = pd.DataFrame(gate_rows)
        m1_gate_threshold_sweep.to_csv(REPORT / "m1_gate_threshold_sweep.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        m1_gate_selected_threshold_summary = m1_gate_threshold_sweep[
            (
                (m1_gate_threshold_sweep["gate"].eq("fault_gate") & m1_gate_threshold_sweep["threshold"].eq(0.50))
                | (m1_gate_threshold_sweep["gate"].eq("pre_event_gate") & m1_gate_threshold_sweep["threshold"].eq(0.60))
                | (m1_gate_threshold_sweep["gate"].isin(["task_gate", "activity_gate"]) & m1_gate_threshold_sweep["threshold"].eq(0.50))
            )
            & m1_gate_threshold_sweep["split"].isin(["validation", "holdout"])
        ].copy()
        m1_gate_selected_threshold_summary.to_csv(
            REPORT / "m1_gate_selected_threshold_summary.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.12g",
            lineterminator="\n",
        )

        gate_reference_rows = []
        selected_gate_map = {"fault_gate": 0.50, "pre_event_gate": 0.60}
        for gate, selected_threshold in selected_gate_map.items():
            for split in ["validation", "holdout"]:
                part = m1_gate_threshold_sweep[
                    m1_gate_threshold_sweep["gate"].eq(gate)
                    & m1_gate_threshold_sweep["split"].eq(split)
                ].copy()
                if part.empty:
                    continue
                selected = part.loc[part["threshold"].eq(selected_threshold)].head(1).copy()
                if not selected.empty:
                    row = selected.iloc[0].to_dict()
                    row.update({"reference_type": "active_runtime_policy", "note": "evidence threshold, not standalone alarm optimum"})
                    gate_reference_rows.append(row)
                balanced = part.sort_values(
                    ["balanced_accuracy", "precision", "false_positive_rate"],
                    ascending=[False, False, True],
                ).head(1)
                if not balanced.empty:
                    row = balanced.iloc[0].to_dict()
                    row.update({"reference_type": "best_balanced_accuracy", "note": "metric reference only"})
                    gate_reference_rows.append(row)
                low_fpr = part.loc[part["false_positive_rate"].le(0.20)].sort_values(
                    ["recall", "precision", "threshold"],
                    ascending=[False, False, True],
                ).head(1)
                if not low_fpr.empty:
                    row = low_fpr.iloc[0].to_dict()
                    row.update({"reference_type": "best_under_fpr_0p20", "note": "strict FPR guardrail reference"})
                    gate_reference_rows.append(row)
                else:
                    gate_reference_rows.append(
                        {
                            "gate": gate,
                            "split": split,
                            "threshold": np.nan,
                            "reference_type": "best_under_fpr_0p20",
                            "note": "no 0.30-0.80 candidate satisfies FPR <= 0.20",
                        }
                    )
        m1_gate_threshold_reference = pd.DataFrame(gate_reference_rows)
        m1_gate_threshold_reference.to_csv(REPORT / "m1_gate_threshold_reference.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        def choose_threshold(part: pd.DataFrame, score: pd.Series, target_fpr: float = 0.20) -> float:
            y = part["label"].eq("pre_fault")
            best = None
            unconstrained_best = None
            for threshold in np.linspace(20.0, 95.0, 31):
                pred = score.ge(threshold)
                tp = int((y & pred).sum())
                fp = int((~y & pred).sum())
                fn = int((y & ~pred).sum())
                tn = int((~y & ~pred).sum())
                precision = tp / max(1, tp + fp)
                recall = tp / max(1, tp + fn)
                fpr = fp / max(1, fp + tn)
                f1 = 2 * precision * recall / max(1e-12, precision + recall)
                if fpr <= target_fpr:
                    candidate = (recall, precision, float(threshold))
                    if best is None or candidate > best:
                        best = candidate
                unconstrained_candidate = (f1, -fpr, float(threshold))
                if unconstrained_best is None or unconstrained_candidate > unconstrained_best:
                    unconstrained_best = unconstrained_candidate
            return (best if best is not None else unconstrained_best)[2]

        hybrid_rows = []
        current_score = pd.to_numeric(m1_scores["current_best_priority_score"], errors="coerce").fillna(0.0)
        m1_specialist_score = pd.to_numeric(m1_scores["m1_specialist_priority_score"], errors="coerce").fillna(0.0)
        for current_best_weight in np.round(np.linspace(0.0, 1.0, 101), 2):
            score = current_best_weight * current_score + (1.0 - current_best_weight) * m1_specialist_score
            validation = m1_scores.loc[m1_scores["split_time_based"].eq("validation")].copy()
            high_threshold = choose_threshold(validation, score.loc[validation.index])
            urgent_threshold = min(95.0, max(high_threshold + 15.0, float(score.loc[validation.index].quantile(0.90))))
            for split, part in m1_scores.groupby("split_time_based", dropna=False):
                pred = score.loc[part.index].ge(high_threshold)
                metrics = binary_metrics(part, pred)
                metrics.update(
                    {
                        "current_best_weight": current_best_weight,
                        "m1_specialist_weight": 1.0 - current_best_weight,
                        "split": split,
                        "high_threshold": high_threshold,
                        "urgent_threshold": urgent_threshold,
                    }
                )
                hybrid_rows.append(metrics)
        hybrid_sweep = pd.DataFrame(hybrid_rows)
        hybrid_sweep["operating_score"] = (
            hybrid_sweep["f1"]
            + 0.20 * hybrid_sweep["fault_event_recall"]
            - 0.50 * hybrid_sweep["false_positive_rate"]
        )
        hybrid_sweep.to_csv(REPORT / "hybrid_weight_sweep.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        def pick_row(name: str, split: str, frame: pd.DataFrame, sort_columns: list[str], ascending: list[bool]) -> dict:
            row = frame.loc[frame["split"].eq(split)].sort_values(sort_columns, ascending=ascending).head(1)
            if row.empty:
                return {"selection_name": name, "split": split}
            payload = row.iloc[0].to_dict()
            payload["selection_name"] = name
            return payload

        holdout_guardrail = hybrid_sweep[
            hybrid_sweep["split"].eq("holdout")
            & hybrid_sweep["fault_event_recall"].ge(0.875)
            & hybrid_sweep["false_positive_rate"].le(0.06)
        ].copy()
        validation_guardrail = hybrid_sweep[
            hybrid_sweep["split"].eq("validation")
            & hybrid_sweep["fault_event_recall"].ge(1.0)
            & hybrid_sweep["false_positive_rate"].le(0.05)
        ].copy()
        summary_candidates = [
            pick_row("final_selected_0p65", "validation", hybrid_sweep[hybrid_sweep["current_best_weight"].round(2).eq(0.65)], ["current_best_weight"], [True]),
            pick_row("final_selected_0p65", "holdout", hybrid_sweep[hybrid_sweep["current_best_weight"].round(2).eq(0.65)], ["current_best_weight"], [True]),
            pick_row("validation_best_f1", "validation", hybrid_sweep, ["f1", "precision", "false_positive_rate"], [False, False, True]),
            pick_row("validation_best_guardrail", "validation", validation_guardrail, ["precision", "f1", "false_positive_rate"], [False, False, True]),
            pick_row("holdout_best_f1", "holdout", hybrid_sweep, ["f1", "precision", "false_positive_rate"], [False, False, True]),
            pick_row("holdout_best_guardrail", "holdout", holdout_guardrail, ["precision", "f1", "false_positive_rate"], [False, False, True]),
            pick_row("holdout_best_operating_score", "holdout", hybrid_sweep, ["operating_score", "precision"], [False, False]),
        ]
        hybrid_selection_summary = pd.DataFrame(summary_candidates)
        hybrid_selection_summary.to_csv(REPORT / "hybrid_weight_selection_summary.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        def evaluate_priority_score(
            frame: pd.DataFrame,
            score: pd.Series,
            *,
            variant: str,
            target_fpr: float = 0.20,
            extra: dict | None = None,
        ) -> list[dict[str, object]]:
            validation = frame.loc[frame["split_time_based"].eq("validation")].copy()
            high_threshold = choose_threshold(validation, score.loc[validation.index], target_fpr=target_fpr)
            validation_scores = score.loc[validation.index]
            urgent_threshold = min(
                95.0,
                max(high_threshold + 15.0, float(validation_scores.quantile(0.90)) if not validation_scores.empty else high_threshold + 15.0),
            )
            rows = []
            for split, part in frame.groupby("split_time_based", dropna=False):
                metrics = binary_metrics(part, score.loc[part.index].ge(high_threshold))
                split_scores = score.loc[part.index].sort_values(ascending=False)
                y_split = part["label"].eq("pre_fault")
                for top_k in [10, 20, 30]:
                    top_idx = split_scores.head(min(top_k, len(split_scores))).index
                    metrics[f"top{top_k}_precision"] = float(y_split.loc[top_idx].mean()) if len(top_idx) else 0.0
                    metrics[f"top{top_k}_recall"] = float(y_split.loc[top_idx].sum() / max(1, y_split.sum()))
                metrics.update(
                    {
                        "variant": variant,
                        "split": split,
                        "high_threshold": high_threshold,
                        "urgent_threshold": urgent_threshold,
                    }
                )
                if extra:
                    metrics.update(extra)
                rows.append(metrics)
            return rows

        pre_event_component = pd.to_numeric(m1_scores["m1_specialist_pre_event_probability"], errors="coerce").fillna(0.0).clip(0, 1)
        leadtime_component = pd.to_numeric(m1_scores["m1_specialist_leadtime_urgency"], errors="coerce").fillna(0.0).clip(0, 1)
        group_component = pd.to_numeric(m1_scores["m1_specialist_group_weight"], errors="coerce").fillna(0.0).clip(0, 1)

        def make_specialist_score(weights: tuple[float, float, float], group_override: float | None = None) -> pd.Series:
            group_values = group_component if group_override is None else pd.Series(group_override, index=m1_scores.index, dtype="float64")
            return 100.0 * (weights[0] * pre_event_component + weights[1] * leadtime_component + weights[2] * group_values)

        specialist_variants = {
            "official_0p55_0p30_0p15": ((0.55, 0.30, 0.15), None),
            "no_pre_event_renorm": ((0.0, 0.30 / 0.45, 0.15 / 0.45), None),
            "no_leadtime_renorm": ((0.55 / 0.70, 0.0, 0.15 / 0.70), None),
            "no_group_renorm": ((0.55 / 0.85, 0.30 / 0.85, 0.0), None),
            "equal_1_3_each": ((1 / 3, 1 / 3, 1 / 3), None),
            "pre_event_only": ((1.0, 0.0, 0.0), None),
            "leadtime_only": ((0.0, 1.0, 0.0), None),
            "group_only": ((0.0, 0.0, 1.0), None),
            "uniform_group_1p0": ((0.55, 0.30, 0.15), 1.0),
            "uniform_group_mean": ((0.55, 0.30, 0.15), float(group_component.mean())),
        }
        specialist_ablation_rows = []
        for variant, (weights, group_override) in specialist_variants.items():
            extra = {
                "w_pre_event": weights[0],
                "w_leadtime": weights[1],
                "w_group": weights[2],
                "group_override": "actual" if group_override is None else str(group_override),
            }
            specialist_ablation_rows.extend(
                evaluate_priority_score(
                    m1_scores,
                    make_specialist_score(weights, group_override),
                    variant=variant,
                    target_fpr=0.20,
                    extra=extra,
                )
            )
        m1_specialist_priority_weight_ablation = pd.DataFrame(specialist_ablation_rows)
        m1_specialist_priority_weight_ablation.to_csv(
            REPORT / "m1_specialist_priority_weight_ablation.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.12g",
            lineterminator="\n",
        )

        specialist_grid_rows = []
        for w_pre in np.round(np.arange(0.0, 1.001, 0.05), 2):
            for w_lead in np.round(np.arange(0.0, 1.0 - w_pre + 0.001, 0.05), 2):
                w_group = round(1.0 - w_pre - w_lead, 2)
                if w_group < -1e-9:
                    continue
                weights = (float(w_pre), float(w_lead), float(w_group))
                specialist_grid_rows.extend(
                    evaluate_priority_score(
                        m1_scores,
                        make_specialist_score(weights),
                        variant=f"grid_{w_pre:.2f}_{w_lead:.2f}_{w_group:.2f}",
                        target_fpr=0.20,
                        extra={"w_pre_event": weights[0], "w_leadtime": weights[1], "w_group": weights[2]},
                    )
                )
        m1_specialist_priority_weight_grid = pd.DataFrame(specialist_grid_rows)
        m1_specialist_priority_weight_grid.to_csv(
            REPORT / "m1_specialist_priority_weight_grid.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.12g",
            lineterminator="\n",
        )

        fault_group_weight_summary = (
            m1_scores.groupby("m1_specialist_fault_group", dropna=False)
            .agg(
                rows=("label", "size"),
                pre_fault_rows=("label", lambda s: int((s == "pre_fault").sum())),
                normal_rows=("label", lambda s: int((s == "normal").sum())),
                fault_events=("fault_event_id", lambda s: int(pd.Series(s).dropna().nunique())),
                group_weight=("m1_specialist_group_weight", "mean"),
                mean_pre_event=("m1_specialist_pre_event_probability", "mean"),
                mean_leadtime_urgency=("m1_specialist_leadtime_urgency", "mean"),
                mean_current_best_priority=("current_best_priority_score", "mean"),
                mean_m1_specialist_priority=("m1_specialist_priority_score", "mean"),
                mean_risk_score=("risk_score", "mean"),
            )
            .reset_index()
        )
        fault_group_weight_summary["pre_fault_rate"] = (
            fault_group_weight_summary["pre_fault_rows"] / fault_group_weight_summary["rows"].clip(lower=1)
        )
        fault_group_weight_summary = fault_group_weight_summary.sort_values("group_weight", ascending=False)
        fault_group_weight_summary.to_csv(REPORT / "fault_group_weight_summary.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        level_calibration_rows = []
        hybrid_score_065 = pd.to_numeric(m1_scores["m1_hybrid_priority_score"], errors="coerce").fillna(0.0)
        for fpr_cap in [0.05, 0.10, 0.15, 0.20]:
            level_calibration_rows.extend(
                evaluate_priority_score(
                    m1_scores,
                    hybrid_score_065,
                    variant="m1_hybrid_0p65_0p35",
                    target_fpr=fpr_cap,
                    extra={"fpr_cap": fpr_cap},
                )
            )
        level_calibration_fpr_cap_sweep = pd.DataFrame(level_calibration_rows)
        level_calibration_fpr_cap_sweep.to_csv(
            REPORT / "level_calibration_fpr_cap_sweep.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.12g",
            lineterminator="\n",
        )

        hybrid_selected_weight_comparison = hybrid_sweep[
            hybrid_sweep["current_best_weight"].round(2).isin([0.65, 0.72, 0.90])
        ].copy()
        hybrid_selected_weight_comparison.to_csv(
            REPORT / "hybrid_selected_weight_comparison.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.12g",
            lineterminator="\n",
        )

        def level_from_score(score: pd.Series, high_threshold: float, urgent_threshold: float) -> pd.Series:
            medium_threshold = max(20.0, high_threshold * 0.60)
            return pd.Series(
                np.select(
                    [score.ge(urgent_threshold), score.ge(high_threshold), score.ge(medium_threshold)],
                    ["urgent", "high", "medium"],
                    default="low",
                ),
                index=score.index,
            )

        compare_weights = [0.65, 0.72]
        score_by_weight = {}
        level_by_weight = {}
        high_label_by_weight = {}
        threshold_by_weight = {}
        for weight in compare_weights:
            key = f"{weight:.2f}".replace(".", "p")
            score = weight * current_score + (1.0 - weight) * m1_specialist_score
            threshold_row = hybrid_sweep[
                hybrid_sweep["split"].eq("validation")
                & hybrid_sweep["current_best_weight"].round(2).eq(weight)
            ].iloc[0]
            high_threshold = float(threshold_row["high_threshold"])
            urgent_threshold = float(threshold_row["urgent_threshold"])
            level = level_from_score(score, high_threshold, urgent_threshold)
            score_by_weight[key] = score
            level_by_weight[key] = level
            high_label_by_weight[key] = level.isin(["high", "urgent"])
            threshold_by_weight[key] = {
                "current_best_weight": weight,
                "m1_specialist_weight": 1.0 - weight,
                "high_threshold": high_threshold,
                "urgent_threshold": urgent_threshold,
            }

        delta_base_columns = [
            "manufacturer", "substation_id", "window_start", "window_end", "label", "fault_event_id",
            "split_time_based", "current_best_priority_score", "m1_specialist_priority_score",
            "current_best_priority_level", "m1_specialist_priority_level",
        ]
        delta_base = m1_scores[[column for column in delta_base_columns if column in m1_scores.columns]].copy()
        delta_base["score_0p65"] = score_by_weight["0p65"]
        delta_base["score_0p72"] = score_by_weight["0p72"]
        delta_base["score_delta_0p72_minus_0p65"] = delta_base["score_0p72"] - delta_base["score_0p65"]
        delta_base["level_0p65"] = level_by_weight["0p65"]
        delta_base["level_0p72"] = level_by_weight["0p72"]
        delta_base["high_label_0p65"] = high_label_by_weight["0p65"].astype("int8")
        delta_base["high_label_0p72"] = high_label_by_weight["0p72"].astype("int8")
        delta_base["level_changed"] = delta_base["level_0p65"].ne(delta_base["level_0p72"])
        delta_base["high_label_changed"] = delta_base["high_label_0p65"].ne(delta_base["high_label_0p72"])
        delta_base["score_delta_formula"] = "0.07 * (current_best_priority_score - m1_specialist_priority_score)"

        metric_compare = hybrid_sweep[
            hybrid_sweep["current_best_weight"].round(2).isin(compare_weights)
            & hybrid_sweep["split"].isin(["train", "validation", "holdout"])
        ].copy()
        metric_columns = [
            "precision", "recall", "f1", "false_positive_rate", "fault_event_recall",
            "tp", "fp", "fn", "tn", "high_threshold", "urgent_threshold",
        ]
        metric_long = metric_compare.melt(
            id_vars=["split", "current_best_weight", "m1_specialist_weight"],
            value_vars=metric_columns,
            var_name="metric",
            value_name="value",
        )
        hybrid_065_vs_072_metric_delta = (
            metric_long
            .pivot_table(index=["split", "metric"], columns="current_best_weight", values="value", aggfunc="first")
            .reset_index()
            .rename(columns={0.65: "value_0p65", 0.72: "value_0p72"})
        )
        hybrid_065_vs_072_metric_delta["delta_0p72_minus_0p65"] = (
            hybrid_065_vs_072_metric_delta["value_0p72"] - hybrid_065_vs_072_metric_delta["value_0p65"]
        )
        hybrid_065_vs_072_metric_delta.to_csv(
            REPORT / "hybrid_065_vs_072_metric_delta.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.12g",
            lineterminator="\n",
        )

        hybrid_065_vs_072_level_transition = (
            delta_base
            .groupby(["split_time_based", "label", "level_0p65", "level_0p72"], dropna=False)
            .size()
            .reset_index(name="rows")
            .sort_values(["split_time_based", "label", "level_0p65", "level_0p72"])
        )
        hybrid_065_vs_072_level_transition.to_csv(
            REPORT / "hybrid_065_vs_072_level_transition.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.12g",
            lineterminator="\n",
        )

        changed_order = [
            "split_time_based", "label", "fault_event_id", "manufacturer", "substation_id",
            "window_start", "window_end", "current_best_priority_score", "m1_specialist_priority_score",
            "score_0p65", "score_0p72", "score_delta_0p72_minus_0p65",
            "level_0p65", "level_0p72", "high_label_0p65", "high_label_0p72",
            "current_best_priority_level", "m1_specialist_priority_level",
        ]
        hybrid_065_vs_072_changed_rows = delta_base.loc[delta_base["level_changed"], [c for c in changed_order if c in delta_base.columns]].copy()
        hybrid_065_vs_072_changed_rows.to_csv(
            REPORT / "hybrid_065_vs_072_changed_rows.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.12g",
            lineterminator="\n",
        )

        component_groups = {
            "Risk": [
                "risk_probability_component_score",
                "risk_episode_component_score",
                "multi_horizon_component_score",
            ],
            "Leadtime": [
                "leadtime_component_score",
                "leadtime_ordinal_component_score",
            ],
            "Anomaly": [
                "anomaly_component_score",
                "multi_window_anomaly_component_score",
            ],
            "Other": [
                "history_adjustment_score",
                "urgency_bonus_score",
            ],
        }
        comp = priority_scores.copy()
        for group, columns in component_groups.items():
            existing = [c for c in columns if c in comp.columns]
            comp[group] = comp[existing].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) if existing else 0.0
        summary_rows = []
        for group in component_groups:
            values = pd.to_numeric(comp[group], errors="coerce").fillna(0.0)
            summary_rows.append(
                {
                    "component_group": group,
                    "mean": float(values.mean()),
                    "median": float(values.median()),
                    "p95": float(values.quantile(0.95)),
                    "max": float(values.max()),
                }
            )
        component_summary = pd.DataFrame(summary_rows)
        component_summary.to_csv(REPORT / "priority_engine_component_summary.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        source_total_rows = int(window_import_meta.get("source_row_count", len(source_current_best_scores)))
        canonical_m1_rows = int(window_import_meta.get("row_count", len(trainable_windows)))
        source_score_total_rows = int(len(source_current_best_scores))
        source_score_m1_rows = int(source_current_best_scores["manufacturer"].astype(str).eq("manufacturer 1").sum())
        final_agent_rows = int(len(m1_scores))
        row_flow_summary = pd.DataFrame(
            [
                {
                    "stage_order": 1,
                    "stage": "source canonical windows",
                    "rows": source_total_rows,
                    "note": "current-best canonical trainable_windows before M1 filter",
                },
                {
                    "stage_order": 2,
                    "stage": "M1 canonical windows",
                    "rows": canonical_m1_rows,
                    "note": "manufacturer 1 only; anomaly and M1 specialist gate can score this scope",
                },
                {
                    "stage_order": 3,
                    "stage": "current-best source score rows",
                    "rows": source_score_total_rows,
                    "note": "risk/leadtime/priority source score rows across both manufacturers",
                },
                {
                    "stage_order": 4,
                    "stage": "current-best M1 score rows",
                    "rows": source_score_m1_rows,
                    "note": "manufacturer 1 rows available from the current-best score bridge",
                },
                {
                    "stage_order": 5,
                    "stage": "final M1 agent rows",
                    "rows": final_agent_rows,
                    "note": "rows retained after joining M1 canonical windows with current-best score bridge",
                },
            ]
        )
        row_flow_summary.to_csv(REPORT / "row_flow_summary.csv", index=False, encoding="utf-8-sig", float_format="%.12g", lineterminator="\n")

        display(Markdown("저장소 루트: 현재 notebook 실행 경로 기준 자동 탐색"))
        display(
            pd.DataFrame(
                [
                    ["source canonical rows", source_total_rows],
                    ["M1 canonical rows", canonical_m1_rows],
                    ["anomaly rows", len(anomaly)],
                    ["M1 specialist scored rows", len(m1_scores)],
                    ["final agent rows", final_agent_rows],
                    ["risk threshold grid rows", len(risk_threshold)],
                    ["hybrid sweep rows", len(hybrid_sweep)],
                    ["criticality sweep rows", len(criticality_sweep)],
                    ["IF/Mahalanobis grid rows", len(anomaly_policy_grid)],
                ],
                columns=["item", "count"],
            )
        )
        """
    ),
    md(
        """
        ## 2. 재학습 흐름과 재현 가능성

        이 저장소는 두 실행 흐름을 분리한다.

        - `all`: 저장소 내부 보존 산출물로 최종 agent card를 재현한다.
        - `full_retrain`: 원천 current-best와 M1 specialist source를 다시 학습한 뒤 모델/metadata/score를 현재 저장소 산출물로 갱신한다.

        따라서 보고서에서 말하는 threshold와 weight는 단순 문서값이 아니라, source 재학습 로그와 저장소 validation 산출물로 다시 확인할 수 있는 값이다.
        """
    ),
    code(
        r"""
        retrain_rows = []
        if source_retrain_meta:
            retrain_rows.append(
                {
                    "stage": "current-best source retrain",
                    "source": source_retrain_meta.get("source_best_root", ""),
                    "steps": " ".join(source_retrain_meta.get("steps", [])),
                    "log_path": source_retrain_meta.get("log_path", ""),
                    "artifact_status": "materialized" if source_retrain_meta.get("materialized_artifacts") else "missing",
                    "note": "risk/leadtime/priority source pipeline regenerated",
                }
            )
        if m1_source_retrain_meta:
            retrain_rows.append(
                {
                    "stage": "M1 specialist source retrain",
                    "source": m1_source_retrain_meta.get("third_project_root", ""),
                    "steps": "run_34_full_gate_joblib_xai4heat_scada_runtime_validation.py",
                    "log_path": m1_source_retrain_meta.get("log_path", ""),
                    "artifact_status": "materialized" if m1_source_retrain_meta.get("materialized_models") else "missing",
                    "note": "fault/task/activity/pre-event gate joblibs regenerated",
                }
            )
        retrain_summary = pd.DataFrame(retrain_rows)
        display(retrain_summary if len(retrain_summary) else Markdown("재학습 metadata가 없으면 `uv run python run_3rd_model_pipeline.py --steps full_retrain`을 먼저 실행한다."))

        if len(retrain_summary):
            fig = px.bar(
                retrain_summary,
                x="stage",
                y=[1] * len(retrain_summary),
                color="artifact_status",
                hover_data=["source", "steps", "log_path", "note"],
                text="artifact_status",
                title="재학습 산출물 Materialize 상태",
            )
            tidy(fig, height=360).update_layout(xaxis_title="", yaxis_title="", showlegend=False)
            fig.show()
        """
    ),
    md(
        """
        ## 3. Row Flow와 표본 수 정리

        이 저장소의 표본 흐름은 아래 3단계로 해석한다.

        ```text
        current-best canonical windows 전체 2526
        -> manufacturer 1만 필터링한 M1 canonical windows 1252
        -> current-best risk/leadtime/priority score bridge와 결합 가능한 M1 final rows 1226
        ```

        별도로 current-best score 산출물은 전체 제조사 기준 2362 rows이고, 이 중 manufacturer 1이 1226 rows다.
        최종 M1 agent flow는 M1 canonical window 1252 rows와 current-best M1 score 1226 rows의 key 교집합을 사용한다.

        빠진 26개 row는 모두 `pre_fault`이고, split 기준으로 train 23개, validation 3개다. Holdout은 183개가 그대로 보존된다.
        이 때문에 최종 성능 비교는 `1226`개 final M1 agent rows를 기준으로 해석하고, anomaly 자체의 분포/threshold 분석은 `1252`개 M1 canonical windows까지 같이 본다.
        """
    ),
    code(
        r"""
        display(row_flow_summary)
        display(row_reconciliation)

        fig = px.bar(
            row_flow_summary,
            x="rows",
            y="stage",
            orientation="h",
            text="rows",
            hover_data=["note"],
            color="stage",
            color_discrete_sequence=[COLORS["gray"], COLORS["blue"], COLORS["teal"], COLORS["orange"], COLORS["green"]],
            title="Row Flow Summary",
        )
        tidy(fig, height=430).update_layout(xaxis_title="rows", yaxis_title="", showlegend=False)
        fig.show()

        missing_summary = (
            missing_agent_windows
            .groupby(["split_time_based", "label"], dropna=False)
            .size()
            .reset_index(name="missing_rows")
        )
        display(missing_summary)

        display(key_coverage_by_artifact)
        fig = px.bar(
            key_coverage_by_artifact,
            x="artifact",
            y="missing_from_target",
            color="missing_pre_fault",
            text="missing_from_target",
            hover_data=["source_rows", "target_rows", "missing_split_distribution", "missing_fault_events"],
            color_continuous_scale="Reds",
            title="Key Coverage Missing Rows by Artifact",
        )
        tidy(fig, height=430).update_layout(xaxis_title="", yaxis_title="missing rows")
        fig.show()
        """
    ),
    md(
        """
        ## 3-1. Agent Card 컬럼 계약

        최종 agent로 넘어가는 기본 card는 두 경로에 같은 내용으로 남는다.

        ```text
        output/agent_priority_card.csv
        output/agent/m1_agent_priority_card.csv
        ```

        둘 다 1226 rows / 55 columns이며, 최종 agent ordering은 `priority_score`, `priority_level`을 따른다.
        이 `priority_score`는 M1 단독 모델이 아니라 current-best priority 65%와 M1 specialist priority 35%를 결합한 hybrid다.

        별도 파일인 `output/agent/m1_specialist_parallel_agent_card.csv`는 1252 rows / 29 columns의 M1 specialist 단독 병렬 산출물이다.
        이 파일은 M1-only evidence 확인용이고, 최종 hybrid agent contract는 아니다.
        """
    ),
    code(
        r"""
        final_column_groups = agent_column_groups[agent_column_groups["card_role"].eq("final_hybrid_agent_card")].copy()
        parallel_column_groups = agent_column_groups[agent_column_groups["card_role"].eq("m1_specialist_parallel_card")].copy()

        final_summary = (
            final_column_groups.groupby(["category", "model_origin", "usage_note"], dropna=False)
            .agg(columns=("column_name", "count"))
            .reset_index()
            .sort_values("columns", ascending=False)
        )
        parallel_summary = (
            parallel_column_groups.groupby(["category", "model_origin", "usage_note"], dropna=False)
            .agg(columns=("column_name", "count"))
            .reset_index()
            .sort_values("columns", ascending=False)
        )
        display(Markdown("**최종 hybrid agent card: 1226 rows / 55 columns**"))
        display(final_summary)
        display(Markdown("**M1 specialist parallel card: 1252 rows / 29 columns**"))
        display(parallel_summary)

        plot_frame = pd.concat(
            [
                final_summary.assign(card="Final hybrid agent card"),
                parallel_summary.assign(card="M1 specialist parallel card"),
            ],
            ignore_index=True,
        )
        fig = px.bar(
            plot_frame,
            x="category",
            y="columns",
            color="card",
            barmode="group",
            text="columns",
            color_discrete_sequence=[COLORS["blue"], COLORS["orange"]],
            title="Agent Card 컬럼 분류: 최종 Hybrid vs M1 단독 Parallel",
        )
        tidy(fig, height=560).update_layout(xaxis_title="", yaxis_title="column count")
        fig.update_xaxes(tickangle=30)
        fig.show()

        contract_focus = final_column_groups[
            final_column_groups["category"].isin(
                [
                    "최종 M1 hybrid priority contract",
                    "M1 specialist 단독 evidence / hybrid input",
                    "Current-best risk 모델",
                    "Current-best leadtime / crossing evidence",
                    "Anomaly evidence / M1 anomaly 모델",
                ]
            )
        ].copy()
        display(contract_focus[[
            "column_order", "column_name", "category", "model_origin",
            "is_final_agent_contract", "is_m1_standalone_evidence", "usage_note"
        ]])
        """
    ),
    md(
        """
        ## 3. Threshold Map

        먼저 현재 저장소에 남아 있는 모든 핵심 threshold를 한 번에 정리한다.

        threshold는 같은 성격이 아니다.

        - anomaly의 q99 threshold는 train-normal 분포 기준선이다.
        - anomaly policy ratio와 criticality는 evidence를 더 보수적으로 만들기 위한 운영 규칙이다.
        - risk threshold는 supervised risk score를 단계화하는 기준이다.
        - priority threshold는 agent가 볼 우선순위 level 기준이다.
        - M1 hybrid threshold는 validation split에서 FPR guardrail을 두고 선택한 high/urgent 기준이다.
        """
    ),
    code(
        r"""
        threshold_map = pd.DataFrame(
            [
                {
                    "area": "Anomaly baseline",
                    "threshold": "train-normal q99",
                    "value": f"IF={anomaly_meta['iforest_threshold']:.6f}, Mahalanobis={anomaly_meta['mahalanobis_threshold']:.3f}",
                    "rationale": "정상 train 분포의 상위 1%를 기준선으로 두고 score ratio를 만든다.",
                },
                {
                    "area": "Anomaly active policy",
                    "threshold": "IF ratio / Mahalanobis ratio",
                    "value": f"{anomaly_meta['iforest_policy_ratio_threshold']} / {anomaly_meta['mahalanobis_policy_ratio_threshold']}",
                    "rationale": "IF는 q99보다 약간 완화해 early evidence를 열고, Mahalanobis는 q99 기준을 유지한다. 두 조건을 동시에 요구한다.",
                },
                {
                    "area": "Anomaly persistence",
                    "threshold": "criticality",
                    "value": str(anomaly_meta["criticality_threshold"]),
                    "rationale": "점 단위 spike보다 지속 이상만 event evidence로 올리기 위한 counter 기준이다.",
                },
                {
                    "area": "Risk level",
                    "threshold": "medium / high / critical (actual M1 output)",
                    "value": "0.22 / 0.92 / 0.92",
                    "rationale": "실제 M1 risk_scores의 applied threshold 기준이다. high와 critical이 같은 0.92이고 critical-first 분류라 M1 output에는 low/medium/critical만 남는다.",
                },
                {
                    "area": "Priority level",
                    "threshold": "medium / high / urgent",
                    "value": f"{priority_meta['priority_level_thresholds']['medium']} / {priority_meta['priority_level_thresholds']['high']} / {priority_meta['priority_level_thresholds']['urgent']}",
                    "rationale": "risk, leadtime, anomaly, 반복 episode를 합친 운영 점수를 agent level로 변환한다.",
                },
                {
                    "area": "M1 specialist level",
                    "threshold": "high / urgent",
                    "value": f"{m1_meta['m1_specialist_thresholds']['high']} / {m1_meta['m1_specialist_thresholds']['urgent']}",
                    "rationale": "validation에서 FPR guardrail을 두고 specialist score의 high/urgent 기준을 잡는다.",
                },
                {
                    "area": "M1 hybrid level",
                    "threshold": "high / urgent",
                    "value": f"{m1_meta['m1_hybrid_thresholds']['high']} / {m1_meta['m1_hybrid_thresholds']['urgent']}",
                    "rationale": "current-best 65%와 M1 specialist 35%를 결합한 점수의 운영 level 기준이다.",
                },
            ]
        )
        display(threshold_map)
        """
    ),
    md(
        """
        ## 4. Anomaly Threshold 근거

        Anomaly는 supervised fault classifier가 아니다. 정상 train 분포에서 벗어난 정도를 보는 evidence 모델이다.
        따라서 anomaly 단독으로 고장 여부를 확정하지 않고, risk/priority 판단을 보강하는 정상 이탈 근거로 둔다.

        최종 판단은 다음 순서로 보수화했다.

        1. train-normal q99를 각 모델의 기준선으로 잡아 ratio를 만든다.
        2. `IF ratio >= 0.90` AND `Mahalanobis ratio >= 1.00`일 때 active policy score가 1 이상이 된다.
        3. 이 상태가 지속되어 `criticality >= 5`가 되면 agent evidence event로 올린다.

        왜 `IF 0.90 / Mahalanobis 1.00`인가:

        - IsolationForest는 국소적/비선형 이탈을 잡지만 단독 사용 시 holdout FPR이 0.113이다. q99보다 약간 낮춘 0.90은 early evidence를 살리기 위한 완화다.
        - Mahalanobis는 공분산 기반 전역 거리라 단독 recall은 더 높지만 holdout FPR이 0.274까지 올라간다. 그래서 1.00, 즉 train-normal q99 기준선을 그대로 유지해 완화하지 않았다.
        - 두 신호를 AND로 묶으면 holdout FPR이 0.075로 내려가고 precision은 0.826이 된다. 즉 IF는 조기 감지 민감도, Mahalanobis는 전역 거리 guardrail 역할을 한다.
        - validation에서는 anomaly 계열이 불안정하다. 이 때문에 anomaly는 최종 high priority를 단독 결정하지 않고 evidence/review reason으로만 둔다.

        왜 `criticality=5`인가:

        - criticality counter는 6시간 window 기준 active anomaly가 지속될 때 +1, 끊기면 -1로 감소한다.
        - `criticality >= 5`는 대략 5개 window, 즉 약 30시간 이상 지속되는 이탈을 요구하는 보수적 기준이다.
        - holdout 기준 criticality 1은 recall 0.532지만 FP 10개가 남는다. criticality 3부터 holdout FP는 0이지만, validation/train normal FP가 여전히 남아 있어 최종 evidence threshold는 5로 더 보수화했다.
        - metric만 보면 criticality 3이 recall은 더 높다. 최종 5는 anomaly를 recall engine이 아니라 신뢰도 높은 persistence evidence로 쓰기 위한 운영 선택점이다.
        """
    ),
    code(
        r"""
        anom_holdout = anomaly_metrics[
            anomaly_metrics["split"].eq("holdout")
            & anomaly_metrics["method"].isin(["iforest_policy", "mahalanobis_policy", "policy_and_point", "policy_and_criticality"])
        ].copy()
        method_label = {
            "iforest_policy": "IF ratio >= 0.90",
            "mahalanobis_policy": "Mahalanobis ratio >= 1.00",
            "policy_and_point": "IF AND Mahalanobis",
            "policy_and_criticality": "Persistent evidence",
        }
        anom_holdout["method_label"] = anom_holdout["method"].map(method_label)
        display(anom_holdout[["method_label", "precision", "recall", "false_positive_rate", "f1", "roc_auc", "average_precision"]])

        anom_long = anom_holdout.melt(
            id_vars=["method_label"],
            value_vars=["precision", "recall", "false_positive_rate"],
            var_name="metric",
            value_name="value",
        )
        anom_long["metric"] = anom_long["metric"].replace(
            {"precision": "Precision", "recall": "Recall", "false_positive_rate": "FPR"}
        )
        fig = px.bar(
            anom_long,
            x="method_label",
            y="value",
            color="metric",
            barmode="group",
            text=anom_long["value"].round(3),
            color_discrete_sequence=[COLORS["blue"], COLORS["green"], COLORS["red"]],
            title="Anomaly 정책별 Holdout 성능 비교",
        )
        tidy(fig, height=460).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()
        """
    ),
    code(
        r"""
        selected_grid = anomaly_policy_grid[
            anomaly_policy_grid["iforest_ratio_threshold"].eq(0.90)
            & anomaly_policy_grid["mahalanobis_ratio_threshold"].eq(1.00)
        ].copy()
        display(selected_grid[[
            "split", "iforest_ratio_threshold", "mahalanobis_ratio_threshold",
            "precision", "recall", "false_positive_rate", "fault_event_recall", "tp", "fp", "fn", "tn"
        ]])

        holdout_grid = anomaly_policy_grid[anomaly_policy_grid["split"].eq("holdout")].copy()
        pivot_fpr = holdout_grid.pivot(
            index="iforest_ratio_threshold",
            columns="mahalanobis_ratio_threshold",
            values="false_positive_rate",
        )
        pivot_recall = holdout_grid.pivot(
            index="iforest_ratio_threshold",
            columns="mahalanobis_ratio_threshold",
            values="recall",
        )

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=["Holdout FPR", "Holdout Recall"],
            horizontal_spacing=0.10,
        )
        fig.add_trace(
            go.Heatmap(
                z=pivot_fpr.values,
                x=pivot_fpr.columns,
                y=pivot_fpr.index,
                coloraxis="coloraxis",
                hovertemplate="Mahalanobis=%{x}<br>IF=%{y}<br>FPR=%{z:.3f}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Heatmap(
                z=pivot_recall.values,
                x=pivot_recall.columns,
                y=pivot_recall.index,
                coloraxis="coloraxis2",
                hovertemplate="Mahalanobis=%{x}<br>IF=%{y}<br>Recall=%{z:.3f}<extra></extra>",
            ),
            row=1,
            col=2,
        )
        for col in [1, 2]:
            fig.add_trace(
                go.Scatter(
                    x=[1.00],
                    y=[0.90],
                    mode="markers+text",
                    marker=dict(size=13, color="black", symbol="x"),
                    text=["0.90 / 1.00"],
                    textposition="top center",
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=1,
                col=col,
            )
        fig.update_layout(
            title="IF / Mahalanobis Threshold Grid",
            coloraxis=dict(colorscale="Reds", colorbar=dict(title="FPR", x=0.46)),
            coloraxis2=dict(colorscale="Greens", colorbar=dict(title="Recall", x=1.02)),
        )
        fig.update_xaxes(title_text="Mahalanobis ratio threshold")
        fig.update_yaxes(title_text="IF ratio threshold")
        tidy(fig, height=520).show()

        guardrail_candidates = holdout_grid[holdout_grid["false_positive_rate"].le(0.08)].copy()
        display(
            guardrail_candidates.sort_values(
                ["recall", "precision", "false_positive_rate"],
                ascending=[False, False, True],
            ).head(12)[[
                "iforest_ratio_threshold", "mahalanobis_ratio_threshold",
                "precision", "recall", "false_positive_rate", "fault_event_recall", "tp", "fp", "fn", "tn"
            ]]
        )
        """
    ),
    md(
        """
        grid 해석:

        - holdout에서 FPR 0.08 이하를 유지하면서 recall을 가장 많이 확보하는 후보군은 IF 0.90 계열이다.
        - IF를 0.95 이상으로 올리면 FPR은 더 줄지만 recall이 크게 감소한다. 이는 anomaly가 risk보다 보조 신호라는 역할에는 지나치게 보수적이다.
        - Mahalanobis threshold는 0.80~1.10 구간에서 holdout 결과가 거의 같지만, 단독 Mahalanobis FPR이 높기 때문에 최종 문서화 기준은 train-normal q99인 1.00으로 고정했다.
        - 따라서 `0.90 / 1.00`은 IF의 early evidence를 살리되 Mahalanobis는 q99 guardrail로 묶는 선택이다.
        """
    ),
    code(
        r"""
        anom_sweep = threshold_sweep[threshold_sweep["score_name"].eq("anomaly_policy_score")].copy()
        fig = go.Figure()
        for metric, color in [("precision", COLORS["blue"]), ("recall", COLORS["green"]), ("false_positive_rate", COLORS["red"])]:
            fig.add_trace(go.Scatter(x=anom_sweep["threshold"], y=anom_sweep[metric], mode="lines+markers", name=metric, line=dict(color=color)))
        fig.add_vline(x=1.0, line_dash="dash", line_color=COLORS["slate"], annotation_text="active score 기준 1.0", annotation_position="top left")
        fig.update_layout(title="Anomaly Policy Score Threshold Sweep", xaxis_title="threshold", yaxis_title="metric value")
        tidy(fig).show()

        crit_holdout = criticality_sweep[criticality_sweep["split"].eq("holdout")].copy()
        fig = go.Figure()
        for metric, color in [("precision", COLORS["blue"]), ("recall", COLORS["green"]), ("false_positive_rate", COLORS["red"]), ("fault_event_recall", COLORS["purple"])]:
            fig.add_trace(go.Scatter(x=crit_holdout["criticality_threshold"], y=crit_holdout[metric], mode="lines+markers", name=metric, line=dict(color=color)))
        fig.add_vline(x=5, line_dash="dash", line_color=COLORS["slate"], annotation_text="최종 criticality=5", annotation_position="top right")
        fig.update_layout(title="Anomaly Criticality Threshold Sweep (Holdout)", xaxis_title="criticality threshold", yaxis_title="metric value")
        tidy(fig).show()

        display(crit_holdout.loc[crit_holdout["criticality_threshold"].isin([1, 3, 5, 7, 10]), [
            "criticality_threshold", "precision", "recall", "false_positive_rate", "fault_event_recall", "tp", "fp", "fn", "tn"
        ]])
        """
    ),
    md(
        """
        criticality 선택 해석:

        - `criticality=1`: active anomaly point를 거의 그대로 쓰는 기준이다. Holdout recall은 0.532로 높지만 FP가 10개 남는다.
        - `criticality=3`: holdout FP가 0으로 떨어지고 recall 0.390을 유지한다. anomaly-only metric만 보면 강한 후보로 볼 수 있다.
        - `criticality=5`: holdout FP 0을 유지하면서 recall은 0.273으로 낮아진다. 대신 더 긴 persistence를 요구하므로 agent에 넘기는 evidence 신뢰도는 더 높다.
        - validation에서는 anomaly persistence 자체가 불안정해 FP가 남고 TP가 거의 없다. 이 때문에 anomaly criticality는 최종 priority의 주 신호가 아니라 `anomaly_evidence_source`, `review_reasons`, priority context에 들어가는 보조 근거로 제한했다.

        따라서 최종 `criticality=5`는 anomaly-only best point가 아니다. 발표/보고에서는 “고장을 많이 잡기 위한 threshold”가 아니라 “정상 이탈이 우연한 spike가 아니라 지속 현상임을 확인하기 위한 evidence threshold”라고 설명해야 한다.
        """
    ),
    md(
        """
        ## 5. Risk Threshold 근거

        risk는 priority engine의 중심 신호다.

        이유:

        - risk는 `pre_fault` 위험 구간을 직접 학습한 supervised 확률이다.
        - threshold grid에서 high 근처는 event recall을 유지하면서 false positive를 크게 낮춘다.
        - medium 기준은 recall을 넓히지만 FPR이 높아 운영 알람보다는 watch 용도다.
        - critical 기준은 precision은 높지만 event를 놓치기 쉬워 최종 priority 단독 기준으로는 너무 좁다.

        단, 실제 M1 저장소 산출물 기준 threshold는 이전 문서의 예시값이 아니라
        `risk_scores.csv` 안의 applied threshold 컬럼을 우선한다.

        ```text
        medium = 0.22
        high = 0.92
        critical = 0.92
        ```

        high와 critical이 같은 값이고 code가 critical을 먼저 판정하므로, 현재 M1 산출물에는 `high` row가 없고
        `low / medium / critical`만 존재한다. 따라서 `0.44`는 현재 M1 output을 설명하는 active threshold로 발표하면 안 된다.
        """
    ),
    code(
        r"""
        display(Markdown("**실제 M1 risk output 적용 threshold**"))
        display(risk_threshold_actual_values)
        display(Markdown("**실제 M1 risk level 분포와 score 범위**"))
        display(risk_level_actual_summary)

        fig = go.Figure()
        for metric, color in [
            ("row_precision", COLORS["blue"]),
            ("row_recall", COLORS["green"]),
            ("false_positive_rate", COLORS["red"]),
            ("event_recall", COLORS["purple"]),
            ("row_f0_5", COLORS["orange"]),
        ]:
            fig.add_trace(go.Scatter(x=risk_threshold["threshold"], y=risk_threshold[metric], mode="lines", name=metric, line=dict(color=color)))
        for x, label, dash, color in [
            (0.22, "medium=0.22", "dash", COLORS["slate"]),
            (0.92, "high/critical=0.92", "dash", COLORS["red"]),
            (0.44, "0.44 reference only", "dot", COLORS["gray"]),
        ]:
            fig.add_vline(x=x, line_dash=dash, line_color=color, annotation_text=label, annotation_position="top")
        fig.update_layout(title="Risk Threshold Selection Grid: 실제 적용 기준과 참고값", xaxis_title="risk threshold", yaxis_title="metric value")
        tidy(fig, height=500).show()

        selected_risk = []
        for target in [0.22, 0.92]:
            row = risk_threshold.iloc[(risk_threshold["threshold"] - target).abs().argsort()[:1]].copy()
            row["selected_label"] = {0.22: "medium", 0.92: "high_and_critical_actual"}[target]
            selected_risk.append(row)
        selected_risk = pd.concat(selected_risk, ignore_index=True)
        display(selected_risk[[
            "selected_label", "threshold", "row_precision", "row_recall", "false_positive_rate",
            "event_recall", "false_positive_episodes", "median_lead_time_hours"
        ]])

        fig = px.histogram(
            risk_scores,
            x="risk_score",
            color="risk_level_calibrated",
            nbins=60,
            opacity=0.75,
            marginal="box",
            color_discrete_sequence=[COLORS["gray"], COLORS["orange"], COLORS["red"], COLORS["blue"]],
            title="Risk Score 분포와 실제 Level 구간",
        )
        fig.add_vline(x=0.22, line_dash="dash", line_color=COLORS["slate"], annotation_text="medium=0.22")
        fig.add_vline(x=0.92, line_dash="dash", line_color=COLORS["red"], annotation_text="high/critical=0.92")
        tidy(fig, height=500).update_layout(xaxis_title="risk_score", yaxis_title="rows")
        fig.show()
        """
    ),
    code(
        r"""
        risk_best = best_pipeline[
            best_pipeline["model"].isin(["previous_promoted_risk", "best_risk_event_temporal"])
            & best_pipeline["metric"].isin(["precision", "recall", "f1", "false_positive_rate", "event_recall"])
        ].copy()
        risk_best["model_label"] = risk_best["model"].replace(
            {
                "previous_promoted_risk": "Previous promoted risk",
                "best_risk_event_temporal": "Current-best risk",
            }
        )
        risk_best["metric"] = risk_best["metric"].replace(
            {"false_positive_rate": "FPR", "event_recall": "Event recall", "precision": "Precision", "recall": "Recall", "f1": "F1"}
        )
        fig = px.bar(
            risk_best,
            x="metric",
            y="value",
            color="model_label",
            barmode="group",
            text=risk_best["value"].round(3),
            color_discrete_sequence=[COLORS["gray"], COLORS["blue"]],
            title="Risk 모델 개선 비교: Previous promoted vs Current-best",
        )
        tidy(fig).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()

        display(risk_event_metrics)
        """
    ),
    md(
        """
        ## 6. Leadtime Threshold / Bucket 근거

        Leadtime은 `0-24h`, `1-3d`, `3-7d` bucket을 예측한다. 이 값은 고장 시각 단정값이 아니라 urgency 참고 신호다.

        priority에서 risk보다 낮은 weight를 주는 이유:

        - leadtime 모델은 pre_fault row에서만 학습된다.
        - holdout top-2 accuracy는 높지만 exact bucket macro F1은 risk의 event-risk 판단보다 낮다.
        - 따라서 leadtime은 “위험한가”보다 “얼마나 가까운가”를 보조하는 역할로 둔다.
        """
    ),
    code(
        r"""
        lead_best = best_pipeline[
            best_pipeline["model"].isin(["previous_promoted_leadtime", "best_leadtime"])
            & best_pipeline["metric"].isin(["accuracy", "macro_f1", "weighted_f1", "top2_accuracy", "bucket_distance_mae"])
        ].copy()
        lead_best["model_label"] = lead_best["model"].replace(
            {
                "previous_promoted_leadtime": "Previous promoted leadtime",
                "best_leadtime": "Current-best leadtime",
            }
        )
        lead_best["metric"] = lead_best["metric"].replace(
            {
                "accuracy": "Accuracy",
                "macro_f1": "Macro F1",
                "weighted_f1": "Weighted F1",
                "top2_accuracy": "Top-2 Acc.",
                "bucket_distance_mae": "Bucket MAE",
            }
        )
        fig = px.bar(
            lead_best,
            x="metric",
            y="value",
            color="model_label",
            barmode="group",
            text=lead_best["value"].round(3),
            color_discrete_sequence=[COLORS["gray"], COLORS["green"]],
            title="Leadtime 모델 개선 비교",
        )
        tidy(fig).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()

        lead_holdout_conf = leadtime_confusion[leadtime_confusion["split"].eq("holdout")].copy()
        fig = px.density_heatmap(
            lead_holdout_conf,
            x="predicted_bucket",
            y="actual_bucket",
            z="count",
            text_auto=True,
            color_continuous_scale="Blues",
            title="Leadtime Holdout Confusion Matrix",
        )
        tidy(fig, height=420).update_layout(xaxis_title="predicted bucket", yaxis_title="actual bucket")
        fig.show()

        display(leadtime_metrics)
        """
    ),
    md(
        """
        ## 7. M1 Specialist Gate Threshold 근거

        M1 specialist gate는 fault/task/activity/pre-event 확률을 만든다.

        현재 사용 기준:

        ```text
        fault / task / activity gate = 0.50
        pre-event gate = 0.60
        ```

        해석상 주의할 점이 있다.

        - 이 값들은 M1 full-gate runtime policy의 evidence threshold다. 최종 알람 threshold나 metric-only optimum으로 주장하지 않는다.
        - `fault_gate`와 `pre_event_gate`는 현재 저장소 안에서 `pre_fault` proxy로 threshold sweep을 확인할 수 있다.
        - `task_gate`는 maintenance/disturbance proxy로만 볼 수 있고, holdout에는 양성 proxy가 거의 없어 성능 주장에 한계가 있다.
        - `activity_gate`는 현재 저장소 안에 native activity label이 없어 true threshold 성능을 주장할 수 없다.
        - fault gate는 FPR을 0.20 이하로 강하게 제한하면 threshold가 올라가고 recall이 크게 낮아진다.
        - pre-event gate는 0.30~0.80 sweep 안에서 FPR <= 0.20 후보가 없어, 독립 알람보다 priority evidence로 쓰는 해석이 맞다.

        따라서 gate threshold는 “완성된 독립 성능 claim”이 아니라 M1 specialist feature를 priority 보조 신호로 만들기 위한 운영 기준이다.
        """
    ),
    code(
        r"""
        selected_gate_thresholds = m1_gate_threshold_sweep[
            (
                (m1_gate_threshold_sweep["gate"].eq("fault_gate") & m1_gate_threshold_sweep["threshold"].eq(0.50))
                | (m1_gate_threshold_sweep["gate"].eq("pre_event_gate") & m1_gate_threshold_sweep["threshold"].eq(0.60))
                | (m1_gate_threshold_sweep["gate"].isin(["task_gate", "activity_gate"]) & m1_gate_threshold_sweep["threshold"].eq(0.50))
            )
            & m1_gate_threshold_sweep["split"].isin(["validation", "holdout"])
        ].copy()
        display(selected_gate_thresholds[[
            "gate", "target_definition", "threshold", "split", "precision", "recall",
            "false_positive_rate", "balanced_accuracy", "positive_rate", "target_positive_count",
            "native_label_available", "tp", "fp", "fn", "tn"
        ]])
        display(Markdown("**선택 threshold와 비교 기준: active runtime policy / balanced accuracy / FPR<=0.20 후보**"))
        display(m1_gate_threshold_reference[[
            "gate", "split", "reference_type", "threshold", "precision", "recall",
            "false_positive_rate", "balanced_accuracy", "tp", "fp", "fn", "tn", "note"
        ]])

        gate_plot = m1_gate_threshold_sweep[
            m1_gate_threshold_sweep["split"].eq("holdout")
            & m1_gate_threshold_sweep["gate"].isin(["fault_gate", "pre_event_gate"])
        ].copy()
        gate_long = gate_plot.melt(
            id_vars=["gate", "threshold", "target_definition"],
            value_vars=["precision", "recall", "false_positive_rate", "balanced_accuracy"],
            var_name="metric",
            value_name="value",
        )
        gate_long["metric"] = gate_long["metric"].replace(
            {
                "precision": "Precision",
                "recall": "Recall",
                "false_positive_rate": "FPR",
                "balanced_accuracy": "Balanced Acc.",
            }
        )
        fig = px.line(
            gate_long,
            x="threshold",
            y="value",
            color="metric",
            facet_col="gate",
            markers=True,
            color_discrete_map={
                "Precision": COLORS["blue"],
                "Recall": COLORS["green"],
                "FPR": COLORS["red"],
                "Balanced Acc.": COLORS["purple"],
            },
            title="M1 Gate Threshold Sweep (Holdout)",
        )
        fig.add_vline(x=0.50, line_dash="dash", line_color=COLORS["slate"], annotation_text="fault=0.50")
        fig.add_vline(x=0.60, line_dash="dot", line_color=COLORS["orange"], annotation_text="pre-event=0.60")
        tidy(fig, height=500).update_layout(xaxis_title="threshold", yaxis_title="metric value")
        fig.show()

        gate_prob_long = gate_eval.melt(
            id_vars=["label", "split_time_based"],
            value_vars=[
                "m1_specialist_fault_probability",
                "m1_specialist_pre_event_probability",
                "m1_specialist_task_probability",
                "m1_specialist_activity_probability",
            ],
            var_name="gate_probability",
            value_name="probability",
        )
        gate_prob_long["gate_probability"] = gate_prob_long["gate_probability"].replace(
            {
                "m1_specialist_fault_probability": "fault",
                "m1_specialist_pre_event_probability": "pre-event",
                "m1_specialist_task_probability": "task",
                "m1_specialist_activity_probability": "activity",
            }
        )
        fig = px.box(
            gate_prob_long,
            x="gate_probability",
            y="probability",
            color="label",
            facet_col="split_time_based",
            points=False,
            color_discrete_map={"normal": COLORS["gray"], "pre_fault": COLORS["red"]},
            title="M1 Gate Probability Distribution by Label",
        )
        fig.add_hline(y=0.50, line_dash="dash", line_color=COLORS["slate"], annotation_text="0.50")
        fig.add_hline(y=0.60, line_dash="dot", line_color=COLORS["orange"], annotation_text="0.60")
        tidy(fig, height=500).update_layout(xaxis_title="", yaxis_title="probability")
        fig.show()
        """
    ),
    md(
        """
        ## 8. M1 Specialist 내부 Priority Weight 근거

        M1 specialist priority 공식:

        ```text
        m1_specialist_priority_score
        = 100 * (
            0.55 * pre_event_probability
          + 0.30 * leadtime_urgency
          + 0.15 * fault_group_weight
        )
        ```

        이 가중치는 metric-only best가 아니다. M1 specialist는 final priority를 단독으로 대체하는 모델이 아니라 current-best priority에 섞이는 보조 evidence다.

        - `pre_event_probability`는 fault 직전 상태를 가장 직접적으로 설명하므로 가장 크게 둔다.
        - `leadtime_urgency`는 위험이 가까운지를 보조하므로 두 번째 축이다.
        - `fault_group_weight`는 group별 severity/monitoring potential을 반영하지만, 현재 산출물에서는 `fault_label`에서 파생된 성격이 강해 live inference에서 그대로 쓸 수 있는지 검토가 필요하다.

        아래 ablation과 grid는 이 한계를 감춘 결과가 아니라, 발표 방어용으로 “어디까지 주장할 수 있고 어디부터 추가 검증이 필요한지”를 분리하기 위한 자료다.
        """
    ),
    code(
        r"""
        ablation_holdout = m1_specialist_priority_weight_ablation[
            m1_specialist_priority_weight_ablation["split"].eq("holdout")
        ].copy()
        important_variants = [
            "official_0p55_0p30_0p15",
            "no_pre_event_renorm",
            "no_leadtime_renorm",
            "no_group_renorm",
            "equal_1_3_each",
            "pre_event_only",
            "leadtime_only",
            "group_only",
            "uniform_group_1p0",
            "uniform_group_mean",
        ]
        ablation_display = ablation_holdout[
            ablation_holdout["variant"].isin(important_variants)
        ].copy()
        display(ablation_display[[
            "variant", "w_pre_event", "w_leadtime", "w_group", "group_override",
            "high_threshold", "precision", "recall", "f1", "false_positive_rate",
            "fault_event_recall", "top10_precision", "top20_precision", "tp", "fp", "fn", "tn"
        ]])

        ablation_long = ablation_display.melt(
            id_vars=["variant"],
            value_vars=["precision", "recall", "f1", "false_positive_rate", "fault_event_recall"],
            var_name="metric",
            value_name="value",
        )
        ablation_long["metric"] = ablation_long["metric"].replace(
            {
                "precision": "Precision",
                "recall": "Recall",
                "f1": "F1",
                "false_positive_rate": "FPR",
                "fault_event_recall": "Event recall",
            }
        )
        fig = px.bar(
            ablation_long,
            x="variant",
            y="value",
            color="metric",
            barmode="group",
            text=ablation_long["value"].round(3),
            color_discrete_map={
                "Precision": COLORS["blue"],
                "Recall": COLORS["green"],
                "F1": COLORS["teal"],
                "FPR": COLORS["red"],
                "Event recall": COLORS["purple"],
            },
            title="M1 Specialist Priority Weight Ablation (Holdout)",
        )
        tidy(fig, height=620).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()
        """
    ),
    code(
        r"""
        grid_holdout = m1_specialist_priority_weight_grid[
            m1_specialist_priority_weight_grid["split"].eq("holdout")
        ].copy()
        deployable_like = grid_holdout[grid_holdout["w_group"].le(0.25)].copy()
        top_grid = grid_holdout.sort_values(
            ["f1", "precision", "false_positive_rate"],
            ascending=[False, False, True],
        ).head(12)
        top_deployable_like = deployable_like.sort_values(
            ["f1", "precision", "false_positive_rate"],
            ascending=[False, False, True],
        ).head(12)
        display(Markdown("**전체 grid 상위 후보 - group weight가 큰 후보는 live inference에서 label-derived risk가 있음**"))
        display(top_grid[[
            "w_pre_event", "w_leadtime", "w_group", "high_threshold",
            "precision", "recall", "f1", "false_positive_rate", "fault_event_recall",
            "tp", "fp", "fn", "tn"
        ]])
        display(Markdown("**group weight <= 0.25로 제한한 후보**"))
        display(top_deployable_like[[
            "w_pre_event", "w_leadtime", "w_group", "high_threshold",
            "precision", "recall", "f1", "false_positive_rate", "fault_event_recall",
            "tp", "fp", "fn", "tn"
        ]])

        fig = px.scatter_ternary(
            grid_holdout,
            a="w_pre_event",
            b="w_leadtime",
            c="w_group",
            color="f1",
            size="recall",
            hover_data=["precision", "false_positive_rate", "fault_event_recall", "high_threshold"],
            color_continuous_scale="Viridis",
            title="M1 Specialist Weight Grid (Holdout F1)",
        )
        fig.add_trace(
            go.Scatterternary(
                a=[0.55],
                b=[0.30],
                c=[0.15],
                mode="markers+text",
                marker=dict(size=14, color="black", symbol="x"),
                text=["official 0.55/0.30/0.15"],
                textposition="top center",
                name="official",
            )
        )
        tidy(fig, height=620).show()
        """
    ),
    code(
        r"""
        display(fault_group_weight_summary[[
            "m1_specialist_fault_group", "rows", "pre_fault_rows", "normal_rows",
            "fault_events", "group_weight", "pre_fault_rate", "mean_pre_event",
            "mean_leadtime_urgency", "mean_risk_score"
        ]])

        fig = px.bar(
            fault_group_weight_summary,
            x="m1_specialist_fault_group",
            y="group_weight",
            color="pre_fault_rate",
            text=fault_group_weight_summary["group_weight"].round(3),
            hover_data=["rows", "pre_fault_rows", "normal_rows", "fault_events", "mean_risk_score"],
            color_continuous_scale="Reds",
            title="Fault Group Weight 근거 요약",
        )
        tidy(fig, height=500).update_layout(xaxis_title="fault group", yaxis_title="group weight")
        fig.show()
        """
    ),
    md(
        """
        M1 specialist weight 해석:

        - 공식 0.55/0.30/0.15는 pre-event를 중심으로 두고 leadtime과 group을 보조로 쓰는 설명 가능한 운영식이다.
        - ablation/grid만 보면 group weight가 큰 후보가 더 좋아 보이는 구간이 있다. 하지만 현재 `fault_group_weight`는 `fault_label` 파생 성격이 강하므로, 새 window에서 사전에 알 수 없는 정보를 쓰는 구조가 아닌지 확인해야 한다.
        - 따라서 group-dominant 후보를 “최고 성능”이라고 채택하지 않았다. 발표에서는 `fault_group_weight`를 고장군 severity/monitoring potential 근거로 설명하되, live inference 계약에서는 별도 calibration 또는 label-free group 추론 로직이 필요하다고 명시해야 한다.
        - task/activity gate는 native label 부재 때문에 최종 보고서에서 독립 성능 claim으로 밀면 안 된다. gate score는 review/evidence 보조 필드로 해석한다.
        """
    ),
    md(
        """
        ## 9. Priority Engine에서 risk weight가 가장 높은 이유

        Priority engine은 단순 확률 모델이 아니라 운영 점수 엔진이다. 그러나 risk가 가장 큰 축으로 들어간다.

        근거는 두 가지다.

        1. 모델 신뢰도: risk는 event-risk를 직접 학습한 supervised signal이고, current-best 개선에서 FPR과 F1이 크게 개선됐다.
        2. 운영 성능: `risk_high_or_critical`은 false positive를 낮게 유지하면서 높은 event recall을 제공한다. leadtime은 시간 근접성, anomaly는 정상 이탈 evidence라서 risk보다 보조 신호에 가깝다.

        component 평균만 보면 leadtime이 높게 보일 수 있다. 이는 거의 모든 scored row에 leadtime reference point가 붙기 때문이다. 실제 운영 우선순위에서는 risk family의 high/critical 단계, 반복 episode, multi-horizon persistence가 상위 priority를 강하게 밀어 올린다.
        """
    ),
    code(
        r"""
        fig = px.bar(
            component_summary.melt(id_vars=["component_group"], value_vars=["mean", "p95", "max"], var_name="summary", value_name="points"),
            x="component_group",
            y="points",
            color="summary",
            barmode="group",
            text="points",
            color_discrete_sequence=[COLORS["blue"], COLORS["orange"], COLORS["purple"]],
            title="Priority Engine Component 기여도 요약",
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        tidy(fig).update_layout(xaxis_title="", yaxis_title="priority points")
        fig.show()

        display(component_summary)

        policy_focus = operational_policy[
            operational_policy["scope"].eq("holdout")
            & operational_policy["policy"].isin(["risk_high_or_critical", "risk_medium_or_higher", "priority_high_or_urgent", "priority_urgent", "anomaly_event", "multi_window_operational", "raw_ae_union"])
        ].copy()
        policy_long = policy_focus.melt(
            id_vars=["policy"],
            value_vars=["event_recall", "normal_false_row_rate", "false_episodes_per_site_month"],
            var_name="metric",
            value_name="value",
        )
        policy_long["metric"] = policy_long["metric"].replace(
            {
                "event_recall": "Event recall",
                "normal_false_row_rate": "Normal FPR",
                "false_episodes_per_site_month": "FP episodes/site-month",
            }
        )
        fig = px.bar(
            policy_long,
            x="policy",
            y="value",
            color="metric",
            barmode="group",
            text=policy_long["value"].round(3),
            color_discrete_sequence=[COLORS["green"], COLORS["red"], COLORS["orange"]],
            title="운영 Policy 비교: risk가 중심축인 이유 (Holdout)",
        )
        tidy(fig, height=520).update_layout(xaxis_title="", yaxis_title="value")
        fig.show()

        display(policy_focus[[
            "policy", "alarm_rows", "normal_false_row_rate", "false_positive_episodes",
            "event_recall", "event_recall_24h", "event_recall_3d", "median_first_alarm_lead_hours"
        ]])
        """
    ),
    code(
        r"""
        scenario_long = priority_weight_sensitivity.melt(
            id_vars=["scenario", "w_risk", "w_leadtime", "w_context"],
            value_vars=["top10_overlap_rate", "review_required_in_top10", "mean_top10_score"],
            var_name="metric",
            value_name="value",
        )
        fig = px.bar(
            scenario_long,
            x="scenario",
            y="value",
            color="metric",
            barmode="group",
            text=scenario_long["value"].round(3),
            color_discrete_sequence=[COLORS["blue"], COLORS["orange"], COLORS["green"]],
            title="Priority Weight Scenario Sensitivity",
        )
        tidy(fig, height=450).update_layout(xaxis_title="", yaxis_title="value")
        fig.show()

        display(priority_weight_sensitivity)
        meta_text = (
            "Priority metadata 기준 risk level point는 `"
            + str(priority_meta["risk_level_points"])
            + "`이고, leadtime bucket point는 `"
            + str(priority_meta["leadtime_bucket_points"])
            + "`이다.\n\nmetadata에도 leadtime은 `"
            + str(priority_meta["leadtime_component"])
            + "`라고 기록돼 있다."
        )
        display(Markdown(meta_text))
        """
    ),
    md(
        """
        ## 10. Level Calibration FPR Cap 근거

        M1 hybrid level calibration에서는 validation split에서 high threshold를 다시 고른다.

        검토한 cap:

        ```text
        FPR cap = 0.05 / 0.10 / 0.15 / 0.20
        ```

        현재 최종 M1 데이터에서는 위 cap들이 모두 같은 high threshold를 선택한다. 즉 `FPR <= 0.20`은 이번 데이터에서 threshold를 느슨하게 만든 직접 원인이 아니라, 향후 validation 분포가 변할 때 recall을 과도하게 죽이지 않기 위한 상한 guardrail이다.

        운영 의미:

        - 0.05처럼 강한 cap은 정상 오탐을 강하게 막는 정책이다.
        - 0.20은 review workflow에서 허용 가능한 상한선이다.
        - 이번 결과에서는 0.05~0.20 모두 같은 기준으로 수렴했으므로, 최종 수치 차이를 부풀려 설명하지 않는다.
        """
    ),
    code(
        r"""
        level_display = level_calibration_fpr_cap_sweep[
            level_calibration_fpr_cap_sweep["split"].isin(["validation", "holdout"])
        ].copy()
        display(level_display[[
            "fpr_cap", "split", "high_threshold", "urgent_threshold",
            "precision", "recall", "f1", "false_positive_rate", "fault_event_recall",
            "top10_precision", "top20_precision", "top30_precision", "tp", "fp", "fn", "tn"
        ]])

        level_long = level_display.melt(
            id_vars=["fpr_cap", "split", "high_threshold", "urgent_threshold"],
            value_vars=["precision", "recall", "f1", "false_positive_rate", "fault_event_recall"],
            var_name="metric",
            value_name="value",
        )
        level_long["metric"] = level_long["metric"].replace(
            {
                "precision": "Precision",
                "recall": "Recall",
                "f1": "F1",
                "false_positive_rate": "FPR",
                "fault_event_recall": "Event recall",
            }
        )
        fig = px.line(
            level_long,
            x="fpr_cap",
            y="value",
            color="metric",
            facet_col="split",
            markers=True,
            color_discrete_map={
                "Precision": COLORS["blue"],
                "Recall": COLORS["green"],
                "F1": COLORS["teal"],
                "FPR": COLORS["red"],
                "Event recall": COLORS["purple"],
            },
            title="Level Calibration FPR Cap 비교",
        )
        tidy(fig, height=500).update_layout(xaxis_title="validation FPR cap", yaxis_title="metric value")
        fig.show()

        threshold_by_cap = level_display.drop_duplicates(["fpr_cap", "split"])[
            ["fpr_cap", "split", "high_threshold", "urgent_threshold", "false_positive_rate"]
        ]
        fig = px.line(
            threshold_by_cap,
            x="fpr_cap",
            y="high_threshold",
            color="split",
            markers=True,
            color_discrete_sequence=[COLORS["orange"], COLORS["green"]],
            title="FPR Cap별 High Threshold",
        )
        tidy(fig, height=420).update_layout(xaxis_title="validation FPR cap", yaxis_title="high threshold")
        fig.show()
        """
    ),
    md(
        """
        ## 11. Hybrid Engine 0.65 / 0.35 근거

        최종 공식:

        ```text
        m1_hybrid_priority_score
        = 0.65 * current_best_priority_score
        + 0.35 * m1_specialist_priority_score
        ```

        해석:

        - current-best는 risk/leadtime/priority 전체 체인을 포함한 운영 baseline이다.
        - M1 specialist는 M1 전용 gate evidence지만 단독으로 쓰면 recall/FPR 균형이 약하다.
        - 0.35는 M1 specialist를 장식이 아니라 실제 score에 반영하는 수준이다.
        - 0.65는 검증된 current-best 체인을 여전히 주축으로 유지한다는 안전장치다.

        아래 sweep은 current-best weight를 0.00부터 1.00까지 바꾸고, 각 weight마다 validation 기준 high threshold를 다시 선택한 결과다.

        중요: 0.65 / 0.35를 “전구간 모든 지표의 절대 best”라고 주장하지 않는다. Holdout precision/F1만 최적화하면 0.72/0.28이나 0.90/0.10처럼 더 current-best 중심인 후보가 같거나 더 좋아 보이는 지표가 있다. 0.65는 validation 안정성, current-best baseline 유지, M1 specialist 반영률을 같이 고려한 운영 선택점이다.
        """
    ),
    code(
        r"""
        official_holdout = m1_compare[m1_compare["split"].eq("holdout") & m1_compare["metric_scope"].eq("row")].copy()
        official_holdout["policy_label"] = official_holdout["policy"].replace(
            {
                "current_best_priority": "Current-best official",
                "m1_specialist_priority": "M1 specialist official",
                "m1_hybrid_priority": "Final hybrid 0.65/0.35",
            }
        )
        off_long = official_holdout.melt(
            id_vars=["policy_label"],
            value_vars=["precision", "recall", "false_positive_rate"],
            var_name="metric",
            value_name="value",
        )
        off_long["metric"] = off_long["metric"].replace(
            {"precision": "Precision", "recall": "Recall", "false_positive_rate": "FPR"}
        )
        fig = px.bar(
            off_long,
            x="metric",
            y="value",
            color="policy_label",
            barmode="group",
            text=off_long["value"].round(3),
            color_discrete_sequence=[COLORS["gray"], COLORS["orange"], COLORS["green"]],
            title="공식 세 정책 비교: Current-best vs M1 specialist vs Hybrid",
        )
        tidy(fig).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()
        display(official_holdout[["policy_label", "precision", "recall", "false_positive_rate", "tp", "fp", "fn", "tn"]])
        """
    ),
    code(
        r"""
        holdout_sweep = hybrid_sweep[hybrid_sweep["split"].eq("holdout")].copy()
        fig = go.Figure()
        for metric, color in [
            ("precision", COLORS["blue"]),
            ("recall", COLORS["green"]),
            ("false_positive_rate", COLORS["red"]),
            ("fault_event_recall", COLORS["purple"]),
        ]:
            fig.add_trace(
                go.Scatter(
                    x=holdout_sweep["current_best_weight"],
                    y=holdout_sweep[metric],
                    mode="lines",
                    name=metric,
                    line=dict(color=color),
                )
            )
        fig.add_vline(x=0.65, line_dash="dash", line_color=COLORS["slate"], annotation_text="최종 0.65 / 0.35", annotation_position="top left")
        fig.add_vline(x=0.72, line_dash="dot", line_color=COLORS["red"], annotation_text="metric-best 후보 0.72 / 0.28", annotation_position="top right")
        fig.add_vline(x=0.90, line_dash="dot", line_color=COLORS["purple"], annotation_text="baseline-heavy 0.90 / 0.10", annotation_position="bottom right")
        fig.update_layout(title="Hybrid Weight Sweep (Holdout)", xaxis_title="current-best weight", yaxis_title="metric value")
        tidy(fig, height=500).show()

        selected_weights = holdout_sweep.loc[
            holdout_sweep["current_best_weight"].isin([0.0, 0.35, 0.5, 0.55, 0.65, 0.72, 0.8, 0.9, 1.0])
        ].copy()
        display(selected_weights[[
            "current_best_weight", "m1_specialist_weight", "high_threshold", "urgent_threshold",
            "precision", "recall", "f1", "false_positive_rate", "fault_event_recall", "tp", "fp", "fn", "tn"
        ]])
        """
    ),
    code(
        r"""
        full_long = hybrid_sweep.melt(
            id_vars=["current_best_weight", "m1_specialist_weight", "split", "high_threshold", "urgent_threshold"],
            value_vars=["precision", "recall", "f1", "false_positive_rate", "fault_event_recall"],
            var_name="metric",
            value_name="value",
        )
        full_long["metric"] = full_long["metric"].replace(
            {
                "precision": "Precision",
                "recall": "Recall",
                "f1": "F1",
                "false_positive_rate": "FPR",
                "fault_event_recall": "Event recall",
            }
        )
        fig = px.line(
            full_long,
            x="current_best_weight",
            y="value",
            color="metric",
            facet_col="split",
            facet_col_wrap=3,
            hover_data=["m1_specialist_weight", "high_threshold", "urgent_threshold"],
            color_discrete_map={
                "Precision": COLORS["blue"],
                "Recall": COLORS["green"],
                "F1": COLORS["teal"],
                "FPR": COLORS["red"],
                "Event recall": COLORS["purple"],
            },
            title="Hybrid Weight 전구간 성능 비교: Train / Validation / Holdout",
        )
        fig.add_vline(x=0.65, line_dash="dash", line_color=COLORS["slate"], annotation_text="0.65")
        fig.add_vline(x=0.72, line_dash="dot", line_color=COLORS["red"], annotation_text="0.72")
        fig.add_vline(x=0.90, line_dash="dot", line_color=COLORS["purple"], annotation_text="0.90")
        tidy(fig, height=560).update_layout(xaxis_title="current-best weight", yaxis_title="metric value")
        fig.show()
        """
    ),
    code(
        r"""
        selection_display = hybrid_selection_summary[
            [
                "selection_name", "split", "current_best_weight", "m1_specialist_weight", "high_threshold",
                "precision", "recall", "f1", "false_positive_rate", "fault_event_recall", "operating_score",
                "tp", "fp", "fn", "tn",
            ]
        ].copy()
        display(selection_display)

        candidate_names = [
            "final_selected_0p65",
            "validation_best_f1",
            "validation_best_guardrail",
            "holdout_best_f1",
            "holdout_best_guardrail",
            "holdout_best_operating_score",
        ]
        candidate_plot = selection_display[selection_display["selection_name"].isin(candidate_names)].copy()
        candidate_long = candidate_plot.melt(
            id_vars=["selection_name", "split", "current_best_weight", "m1_specialist_weight"],
            value_vars=["precision", "recall", "f1", "false_positive_rate", "fault_event_recall"],
            var_name="metric",
            value_name="value",
        )
        candidate_long["metric"] = candidate_long["metric"].replace(
            {
                "precision": "Precision",
                "recall": "Recall",
                "f1": "F1",
                "false_positive_rate": "FPR",
                "fault_event_recall": "Event recall",
            }
        )
        candidate_long["label"] = (
            candidate_long["selection_name"]
            + " | "
            + candidate_long["split"]
            + " | w="
            + candidate_long["current_best_weight"].round(2).astype(str)
        )
        fig = px.bar(
            candidate_long,
            x="label",
            y="value",
            color="metric",
            barmode="group",
            text=candidate_long["value"].round(3),
            color_discrete_map={
                "Precision": COLORS["blue"],
                "Recall": COLORS["green"],
                "F1": COLORS["teal"],
                "FPR": COLORS["red"],
                "Event recall": COLORS["purple"],
            },
            title="0.65와 metric-best 후보 비교",
        )
        tidy(fig, height=620).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()
        """
    ),
    code(
        r"""
        score_fig = px.line(
            hybrid_sweep,
            x="current_best_weight",
            y="operating_score",
            color="split",
            hover_data=[
                "precision", "recall", "f1", "false_positive_rate", "fault_event_recall",
                "m1_specialist_weight", "high_threshold",
            ],
            color_discrete_sequence=[COLORS["blue"], COLORS["orange"], COLORS["green"]],
            title="Hybrid Weight Operating Score 전구간 비교",
        )
        score_fig.add_vline(x=0.65, line_dash="dash", line_color=COLORS["slate"], annotation_text="0.65")
        score_fig.add_vline(x=0.72, line_dash="dot", line_color=COLORS["red"], annotation_text="0.72")
        score_fig.add_vline(x=0.90, line_dash="dot", line_color=COLORS["purple"], annotation_text="0.90")
        tidy(score_fig).update_layout(xaxis_title="current-best weight", yaxis_title="F1 + 0.2*event recall - 0.5*FPR")
        score_fig.show()

        pr = hybrid_sweep[hybrid_sweep["split"].isin(["validation", "holdout"])].copy()
        fig = px.scatter(
            pr,
            x="recall",
            y="precision",
            color="false_positive_rate",
            symbol="split",
            size="fault_event_recall",
            hover_data=["current_best_weight", "m1_specialist_weight", "f1", "high_threshold", "tp", "fp", "fn", "tn"],
            color_continuous_scale="RdYlGn_r",
            title="Hybrid Weight Precision-Recall Trade-off (색상=FPR, 크기=Event Recall)",
        )
        selected = pr[pr["current_best_weight"].round(2).eq(0.65)]
        candidate_072 = pr[pr["current_best_weight"].round(2).eq(0.72)]
        candidate_090 = pr[pr["current_best_weight"].round(2).eq(0.90)]
        fig.add_trace(
            go.Scatter(
                x=selected["recall"],
                y=selected["precision"],
                mode="markers+text",
                text=["0.65 " + s for s in selected["split"].astype(str)],
                textposition="top center",
                marker=dict(size=16, color="black", symbol="x"),
                name="selected 0.65",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=candidate_072["recall"],
                y=candidate_072["precision"],
                mode="markers+text",
                text=["0.72 " + s for s in candidate_072["split"].astype(str)],
                textposition="bottom center",
                marker=dict(size=14, color=COLORS["red"], symbol="diamond"),
                name="candidate 0.72",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=candidate_090["recall"],
                y=candidate_090["precision"],
                mode="markers+text",
                text=["0.90 " + s for s in candidate_090["split"].astype(str)],
                textposition="middle right",
                marker=dict(size=14, color=COLORS["purple"], symbol="square"),
                name="baseline-heavy 0.90",
            )
        )
        tidy(fig, height=520).update_layout(xaxis_title="Recall", yaxis_title="Precision")
        fig.show()
        """
    ),
    code(
        r"""
        selected_weight_table = hybrid_selected_weight_comparison[
            hybrid_selected_weight_comparison["split"].isin(["validation", "holdout"])
        ].copy()
        display(selected_weight_table[[
            "split", "current_best_weight", "m1_specialist_weight", "high_threshold", "urgent_threshold",
            "precision", "recall", "f1", "false_positive_rate", "fault_event_recall",
            "tp", "fp", "fn", "tn"
        ]].sort_values(["split", "current_best_weight"]))

        selected_weight_long = selected_weight_table.melt(
            id_vars=["split", "current_best_weight", "m1_specialist_weight"],
            value_vars=["precision", "recall", "f1", "false_positive_rate", "fault_event_recall"],
            var_name="metric",
            value_name="value",
        )
        selected_weight_long["weight_label"] = (
            selected_weight_long["current_best_weight"].round(2).astype(str)
            + " / "
            + selected_weight_long["m1_specialist_weight"].round(2).astype(str)
        )
        selected_weight_long["metric"] = selected_weight_long["metric"].replace(
            {
                "precision": "Precision",
                "recall": "Recall",
                "f1": "F1",
                "false_positive_rate": "FPR",
                "fault_event_recall": "Event recall",
            }
        )
        fig = px.bar(
            selected_weight_long,
            x="weight_label",
            y="value",
            color="metric",
            facet_col="split",
            barmode="group",
            text=selected_weight_long["value"].round(3),
            color_discrete_map={
                "Precision": COLORS["blue"],
                "Recall": COLORS["green"],
                "F1": COLORS["teal"],
                "FPR": COLORS["red"],
                "Event recall": COLORS["purple"],
            },
            title="Selected Hybrid Weights 비교: 0.65/0.35 vs 0.72/0.28 vs 0.90/0.10",
        )
        tidy(fig, height=560).update_layout(xaxis_title="current-best / M1 specialist", yaxis_title="metric value")
        fig.show()
        """
    ),
    md(
        """
        ## 12. 0.65/0.35에서 0.72/0.28 또는 0.90/0.10으로 바꿀 때

        0.72/0.28은 current-best 반영률을 7%p 올리고 M1 specialist 반영률을 7%p 낮추는 설정이다.
        이번 sweep에서는 0.65와 0.72 모두 validation 기준 high threshold가 67.5, urgent threshold가 82.5로 동일했다.
        따라서 아래 비교는 threshold 변경 효과가 아니라 weight 변경 효과로 해석할 수 있다.

        0.90/0.10은 current-best를 거의 유지하는 baseline-heavy 비교군이다. Holdout에서는 0.72/0.28과 같은 row-level 성능으로 관측되지만, M1 specialist 반영률이 10%로 줄어 최종 저장소에서 M1 specialist를 별도 반영했다는 설명력은 약해진다.

        점수 변화식은 다음과 같다.

        ```text
        score_0.72 - score_0.65
        = 0.07 * (current_best_priority_score - m1_specialist_priority_score)
        ```

        즉 current-best가 M1 specialist보다 높은 행은 올라가고, M1 specialist가 current-best보다 높은 행은 내려간다.
        """
    ),
    code(
        r"""
        key_metrics = ["precision", "recall", "f1", "false_positive_rate", "fault_event_recall"]
        metric_name_map = {
            "precision": "Precision",
            "recall": "Recall",
            "f1": "F1",
            "false_positive_rate": "FPR",
            "fault_event_recall": "Event recall",
            "tp": "TP",
            "fp": "FP",
            "fn": "FN",
            "tn": "TN",
            "high_threshold": "High threshold",
            "urgent_threshold": "Urgent threshold",
        }

        delta_metrics = hybrid_065_vs_072_metric_delta.copy()
        delta_metrics["metric_label"] = delta_metrics["metric"].map(metric_name_map).fillna(delta_metrics["metric"])
        display(
            delta_metrics[
                delta_metrics["metric"].isin(["precision", "recall", "f1", "false_positive_rate", "fault_event_recall", "tp", "fp", "fn", "tn"])
            ].sort_values(["split", "metric"])
        )

        metric_delta_plot = delta_metrics[delta_metrics["metric"].isin(key_metrics)].copy()
        fig = px.bar(
            metric_delta_plot,
            x="metric_label",
            y="delta_0p72_minus_0p65",
            color="split",
            barmode="group",
            text=metric_delta_plot["delta_0p72_minus_0p65"].round(4),
            color_discrete_sequence=[COLORS["blue"], COLORS["orange"], COLORS["green"]],
            title="0.65에서 0.72 변경 시 성능 변화",
        )
        fig.add_hline(y=0, line_color=COLORS["slate"], line_width=1)
        tidy(fig, height=480).update_layout(xaxis_title="", yaxis_title="0.72 - 0.65")
        fig.show()
        """
    ),
    code(
        r"""
        score_delta_summary = (
            delta_base
            .groupby(["split_time_based", "label"], dropna=False)["score_delta_0p72_minus_0p65"]
            .describe(percentiles=[0.25, 0.5, 0.75])
            .reset_index()
        )
        display(score_delta_summary)

        fig = px.box(
            delta_base,
            x="split_time_based",
            y="score_delta_0p72_minus_0p65",
            color="label",
            points="outliers",
            color_discrete_sequence=[COLORS["gray"], COLORS["red"]],
            title="Score 변화 분포 (0.72 - 0.65)",
        )
        fig.add_hline(y=0, line_color=COLORS["slate"], line_width=1)
        tidy(fig, height=480).update_layout(xaxis_title="split", yaxis_title="score delta")
        fig.show()
        """
    ),
    code(
        r"""
        transition = hybrid_065_vs_072_level_transition.copy()
        transition["transition"] = transition["level_0p65"] + " → " + transition["level_0p72"]
        display(transition.sort_values(["split_time_based", "label", "level_0p65", "level_0p72"]))

        changed_transition = transition[transition["level_0p65"].ne(transition["level_0p72"])].copy()
        fig = px.bar(
            changed_transition,
            x="transition",
            y="rows",
            color="split_time_based",
            facet_col="label",
            text="rows",
            color_discrete_sequence=[COLORS["blue"], COLORS["orange"], COLORS["green"]],
            title="0.65에서 0.72 변경 시 Level 이동",
        )
        tidy(fig, height=520).update_layout(xaxis_title="level transition", yaxis_title="rows")
        fig.show()

        changed_count = int(delta_base["level_changed"].sum())
        total_count = int(len(delta_base))
        high_label_changed_count = int(delta_base["high_label_changed"].sum())
        display(
            pd.DataFrame(
                [
                    ["total rows", total_count],
                    ["level changed rows", changed_count],
                    ["high-label changed rows", high_label_changed_count],
                    ["unchanged rows", total_count - changed_count],
                ],
                columns=["item", "count"],
            )
        )
        """
    ),
    code(
        r"""
        changed_examples = hybrid_065_vs_072_changed_rows.copy()
        changed_examples["abs_score_delta"] = changed_examples["score_delta_0p72_minus_0p65"].abs()
        display(
            changed_examples.sort_values(
                ["split_time_based", "high_label_0p65", "high_label_0p72", "abs_score_delta"],
                ascending=[True, False, True, False],
            ).head(30)
        )
        """
    ),
    md(
        """
        해석:

        - 0.72/0.28은 관측 지표만 보면 0.65/0.35보다 약간 좋다. Holdout에서 FP가 6에서 5로 줄고, precision과 FPR이 개선된다. Validation도 FP가 7에서 6으로 줄며 recall은 유지된다.
        - 대신 M1 specialist 반영률이 35%에서 28%로 낮아진다. Specialist만 강하게 올린 중간 review 후보가 더 많이 낮아지고, current-best가 강하게 올린 행은 high/urgent 쪽으로 유지되거나 일부 상승한다.
        - 따라서 “holdout metric best”를 최우선으로 쓰면 0.72/0.28이 더 방어 가능하다. 반대로 M1 specialist를 최종 agent 흐름에 의미 있게 반영한다는 설명력까지 같이 잡으면 0.65/0.35가 더 보수적인 운영 선택점이다.
        """
    ),
    md(
        """
        ## 13. 최종 판단

        Threshold와 weight는 모두 같은 기준으로 정한 것이 아니라 각 모델의 역할에 맞춰 정했다.

        - anomaly: 정상 분포 이탈 evidence. 단독 recall보다 FPR 억제와 지속성 확인이 중요하다.
        - risk: pre_fault 위험을 직접 학습한 핵심 신호. priority engine에서 가장 높은 비중을 가져가는 것이 타당하다.
        - leadtime: 위험 여부가 아니라 시간 근접성을 보조한다. exact bucket 오차가 있으므로 risk보다 낮게 둔다.
        - priority engine: risk 중심 + leadtime urgency + anomaly/episode context의 운영 점수 구조다.
        - hybrid 0.65/0.35: current-best를 baseline으로 유지하되 M1 specialist evidence를 실제 우선순위에 반영하는 절충점이다.
        - M1 gate 0.50/0.60: 최종 알람 임계값이 아니라 specialist evidence를 만드는 runtime policy다.
        - 실제 M1 risk level: `medium=0.22`, `high=0.92`, `critical=0.92`; critical-first 판정 때문에 현재 M1 output에는 `high` level row가 없다.

        보고 시 주의:

        - 0.65/0.35는 유일한 수학적 optimum이 아니다. Holdout precision/F1만 보면 0.72/0.28 또는 0.90/0.10이 같거나 더 좋은 지표를 보인다.
        - 최종 0.65는 holdout을 직접 최적화한 값이 아니라 validation 안정성, baseline 유지, specialist 반영률을 같이 본 운영 선택점이다.
        - 0.90/0.10은 current-best 유지에는 강하지만 M1 specialist 반영률이 10%뿐이라 M1 specialist package의 목적과 설명력이 약해진다.
        - M1 specialist 내부 ablation에서 group-heavy 후보가 좋아 보이는 것은 `fault_group_weight`의 label-derived 성격 때문일 수 있으므로 live inference 성능으로 단정하지 않는다.
        - fault/pre-event gate도 독립 알람 threshold가 아니라 evidence threshold로 설명한다. task/activity gate는 native label이 없어 proxy 또는 산출물 존재 확인 수준으로만 설명한다.
        - holdout fault event 수가 작으므로 event recall은 절대 확정값이 아니라 방향성 근거로 해석한다.
        - priority score는 자동 정비 지시가 아니라 사람이 먼저 볼 설비를 정렬하는 운영 신호다.
        """
    ),
]

OUT.parent.mkdir(parents=True, exist_ok=True)
for idx, cell in enumerate(nb.cells):
    cell["id"] = f"cell-{idx:03d}"
OUT.write_text(nbf.writes(nb), encoding="utf-8", newline="\n")
print(f"Wrote {OUT}")
