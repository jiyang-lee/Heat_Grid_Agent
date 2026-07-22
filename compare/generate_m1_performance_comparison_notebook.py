from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
OUT = PACKAGE_ROOT / "compare" / "m1_specialist_performance_comparison.ipynb"


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
        # M1 Specialist 최종본 도출 성능비교

        발표 및 보고용 요약 노트북이다. 비교 대상은 최종 의사결정에 실제로 영향을 준 후보만 남겼다.

        최종 결론:

        ```text
        최종 M1 agent priority
        = 0.65 * current-best priority
        + 0.35 * M1 specialist priority
        ```

        도출 이유:

        - anomaly는 단독 고장 판정기가 아니라 evidence 신호로 쓰는 것이 타당했다.
        - current-best risk/leadtime/priority 체인은 기존 promoted 후보보다 안정적인 baseline이었다.
        - priority LGBM 단독 후보는 holdout에서 rule-based priority를 대체할 만큼 안정적이지 않았다.
        - M1 specialist 단독은 보조 근거로는 의미가 있지만 단독 운영 모델로는 precision/recall 균형이 약했다.
        - M1 hybrid는 current-best 대비 recall 일부를 희생하는 대신 false positive rate를 크게 낮추고 fault-event recall을 유지했다.
        """
    ),
    md(
        """
        ## 1. 분석 범위와 신뢰도

        사용한 근거는 모두 로컬 산출물 CSV/JSON에 남아 있는 값이다.

        | 구분 | 사용 근거 | 신뢰도 |
        | --- | --- | --- |
        | 최종 M1 비교 | `output/reports/m1_specialist_vs_current_best_comparison.csv` | 높음 |
        | 최종 M1 anomaly | `output/anomaly_metrics.csv` | 높음 |
        | 최종 active policy ablation | `output/reports/ablation_summary.csv` | 높음 |
        | current-best 개선 비교 | `artifacts/current_best/reports/best_pipeline_comparison.csv` | 높음 |
        | risk/leadtime 후보 비교 | `artifacts/current_best/experiment_traces/report_compare/*_experiment_comparison.csv` | 중간-높음 |
        | priority rule vs LGBM 비교 | `artifacts/current_best/experiment_traces/priority_compare/*metrics.csv` | 중간-높음 |

        제외한 것:

        - feature leakage 검토 전 결과
        - 비교 축이 달라 발표에서 오해될 수 있는 중간 실험
        - 최종 모델 선택에 직접 영향을 주지 못한 폐기성 후보
        """
    ),
    code(
        r"""
        import os
        from pathlib import Path
        import json
        import numpy as np
        import pandas as pd
        from IPython.display import display, Markdown
        import plotly.express as px
        import plotly.io as pio

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
                    (candidate / "output/reports/m1_specialist_vs_current_best_comparison.csv").exists()
                    and (candidate / "artifacts/current_best").exists()
                ):
                    return candidate
            raise FileNotFoundError("M1 specialist repository root not found. Set M1_SPECIALIST_REPO_ROOT.")

        PKG = find_repo_root()
        ART = PKG / "artifacts" / "current_best"

        COLORS = {
            "blue": "#2563EB",
            "green": "#16A34A",
            "red": "#DC2626",
            "orange": "#F97316",
            "teal": "#0891B2",
            "purple": "#7C3AED",
            "gray": "#64748B",
        }

        def read_csv(path: Path) -> pd.DataFrame:
            if not path.exists():
                raise FileNotFoundError(path)
            return pd.read_csv(path)

        files = {
            "m1_compare": PKG / "output/reports/m1_specialist_vs_current_best_comparison.csv",
            "m1_anomaly": PKG / "output/anomaly_metrics.csv",
            "ablation": PKG / "output/reports/ablation_summary.csv",
            "row_reconciliation": PKG / "output/reports/row_reconciliation.csv",
            "pipeline_metadata": PKG / "output/reports/pipeline_run_metadata.json",
            "best_pipeline": ART / "reports/best_pipeline_comparison.csv",
            "risk_experiment": ART / "experiment_traces/report_compare/risk_holdout_experiment_comparison.csv",
            "leadtime_experiment": ART / "experiment_traces/report_compare/leadtime_holdout_experiment_comparison.csv",
            "priority_lgbm_rule_class": ART / "experiment_traces/priority_compare/priority_lgbm_vs_rule_classification_metrics.csv",
            "priority_lgbm_rule_topk": ART / "experiment_traces/priority_compare/priority_lgbm_vs_rule_topk_metrics.csv",
        }

        data = {name: read_csv(path) for name, path in files.items() if path.suffix == ".csv"}
        with open(files["pipeline_metadata"], "r", encoding="utf-8") as f:
            metadata = json.load(f)
        def read_optional_json(path: Path) -> dict:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        source_retrain = read_optional_json(PKG / "output/reports/source_retrain_metadata.json")
        m1_source_retrain = read_optional_json(PKG / "output/reports/m1_source_retrain_metadata.json")

        def tidy(fig, height=430):
            fig.update_layout(
                template="plotly_white",
                height=height,
                title_x=0.02,
                font=dict(size=13),
                legend_title="",
                margin=dict(l=40, r=20, t=70, b=70),
            )
            return fig

        source_summary = pd.DataFrame(
            [
                ["M1 final comparison", "m1_specialist_vs_current_best_comparison.csv", len(data["m1_compare"])],
                ["M1 anomaly comparison", "anomaly_metrics.csv", len(data["m1_anomaly"])],
                ["M1 active ablation", "ablation_summary.csv", len(data["ablation"])],
                ["Risk/leadtime current-best", "best_pipeline_comparison.csv", len(data["best_pipeline"])],
                ["Risk candidates", "risk_holdout_experiment_comparison.csv", len(data["risk_experiment"])],
                ["Leadtime candidates", "leadtime_holdout_experiment_comparison.csv", len(data["leadtime_experiment"])],
                ["Priority rule vs LGBM", "priority_lgbm_vs_rule_*metrics.csv", len(data["priority_lgbm_rule_class"])],
            ],
            columns=["evidence_group", "file", "rows"],
        )
        display(source_summary)
        retrain_summary = pd.DataFrame(
            [
                {
                    "stage": "current-best source retrain",
                    "source": source_retrain.get("source_best_root", ""),
                    "log_path": source_retrain.get("log_path", ""),
                    "status": "available" if source_retrain else "not_run_in_package",
                },
                {
                    "stage": "M1 specialist source retrain",
                    "source": m1_source_retrain.get("third_project_root", ""),
                    "log_path": m1_source_retrain.get("log_path", ""),
                    "status": "available" if m1_source_retrain else "not_run_in_package",
                },
            ]
        )
        display(retrain_summary)
        display(Markdown(f"최종 산출물 생성 시각: `{metadata['generated_at_utc']}`"))
        """
    ),
    md(
        """
        ## 2. 최종본까지의 후보 정리

        전체 실험을 전부 나열하지 않고, 최종 판단을 설명하는 후보만 남겼다.
        """
    ),
    code(
        r"""
        decision_funnel = pd.DataFrame(
            [
                ["Anomaly 단독 정책", "정상 분포 이탈을 포착하지만 recall/FPR 균형이 정책별로 크게 다름", "단독 알람보다 evidence로 사용"],
                ["기존 promoted risk/leadtime", "holdout 성능과 FPR/MAE 기준에서 current-best보다 약함", "current-best 체인으로 교체"],
                ["Current-best risk/leadtime/priority", "risk event recall과 priority ranking이 안정적", "최종 M1 baseline body로 유지"],
                ["LGBM priority head", "holdout에서 rule-based priority보다 action F1/NDCG@R이 낮음", "운영 baseline 교체 후보에서 제외"],
                ["M1 specialist gate", "M1 전용 evidence는 제공하지만 단독 운영 성능은 약함", "35% 보조 신호로 결합"],
                ["M1 hybrid priority", "precision 향상, FPR 감소, fault-event recall 유지", "최종본 채택"],
            ],
            columns=["stage", "finding", "decision"],
        )
        display(decision_funnel)
        """
    ),
    md(
        """
        ## 3. Anomaly 비교: 왜 evidence 역할로 남겼는가

        Anomaly 모델은 “고장 확률”을 직접 예측한다기보다 정상 운전 분포에서 벗어난 정도를 측정한다.
        그래서 최종 contract에서는 anomaly를 단독 판정으로 쓰지 않고 risk/priority 판단을 보강하는 evidence로 남겼다.

        대표 비교 해석:

        - `iforest_policy`: recall은 중간 수준이나 FPR이 남는다.
        - `mahalanobis_policy`: recall은 가장 높지만 FPR이 높아 단독 알람으로 부담이 크다.
        - `policy_and_point`: IF와 Mahalanobis 근거를 함께 보는 균형안이다.
        - `policy_and_criticality`: FPR 0에 가까운 강한 확인 신호지만 recall이 낮아 단독 주 정책으로는 부족하다.
        """
    ),
    code(
        r"""
        anom = data["m1_anomaly"].copy()
        anom_h = anom[
            anom["split"].eq("holdout")
            & anom["method"].isin(["iforest_policy", "mahalanobis_policy", "policy_and_point", "policy_and_criticality"])
        ].copy()
        method_label = {
            "iforest_policy": "IsolationForest",
            "mahalanobis_policy": "Mahalanobis",
            "policy_and_point": "IF + Mahalanobis",
            "policy_and_criticality": "Persistent evidence",
        }
        anom_h["method_label"] = anom_h["method"].map(method_label)
        display(anom_h[["method_label", "row_count", "precision", "recall", "f1", "false_positive_rate", "roc_auc"]])

        anom_long = anom_h.melt(
            id_vars=["method_label"],
            value_vars=["precision", "recall", "f1", "false_positive_rate"],
            var_name="metric",
            value_name="value",
        )
        anom_long["metric"] = anom_long["metric"].replace(
            {
                "precision": "Precision",
                "recall": "Recall",
                "f1": "F1",
                "false_positive_rate": "FPR",
            }
        )
        fig = px.bar(
            anom_long,
            x="method_label",
            y="value",
            color="metric",
            barmode="group",
            text=anom_long["value"].round(3),
            color_discrete_sequence=[COLORS["blue"], COLORS["green"], COLORS["purple"], COLORS["red"]],
            title="M1 Anomaly 대표 정책 비교 (Holdout)",
        )
        tidy(fig, height=460).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()
        """
    ),
    md(
        """
        ## 4. Risk 비교: current-best risk를 baseline으로 둔 이유

        risk는 최종 priority의 중심 신호다. 여기서는 모든 drift/feature ablation을 넣지 않고,
        의사결정에 필요한 대표 후보만 비교한다.

        - `Official base`: calibration 전 기준선이다.
        - `Official calibrated`: FPR과 precision은 개선되지만 recall이 일부 줄어든다.
        - `Promoted candidate`: 당시 promoted 후보였지만 current-best보다 약했다.
        - `Current-best risk`: event-temporal 보강 후 precision/F1/FPR이 가장 안정적이다.
        """
    ),
    code(
        r"""
        risk_exp = data["risk_experiment"].copy()
        risk_keep = risk_exp[
            ((risk_exp["source"].eq("official_base")) & (risk_exp["variant"].eq("official_base_raw")))
            | ((risk_exp["source"].eq("official_calibrated")) & (risk_exp["variant"].eq("official_calibrated")))
            | ((risk_exp["source"].eq("promoted_candidate")) & (risk_exp["variant"].eq("promoted_calibrated")))
        ].copy()
        risk_keep["model_label"] = risk_keep["source"].map(
            {
                "official_base": "Official base",
                "official_calibrated": "Official calibrated",
                "promoted_candidate": "Promoted candidate",
            }
        )

        best = data["best_pipeline"].copy()
        best_risk_values = best[
            (best["model"].eq("best_risk_event_temporal"))
            & best["metric"].isin(["roc_auc", "average_precision", "precision", "recall", "f1", "false_positive_rate"])
        ].set_index("metric")["value"].to_dict()
        current_best = pd.DataFrame(
            [
                {
                    "model_label": "Current-best Risk",
                    "roc_auc": best_risk_values["roc_auc"],
                    "average_precision": best_risk_values["average_precision"],
                    "precision": best_risk_values["precision"],
                    "recall": best_risk_values["recall"],
                    "f1": best_risk_values["f1"],
                    "fpr": best_risk_values["false_positive_rate"],
                }
            ]
        )
        risk_keep = risk_keep.rename(columns={"false_positive_rate": "fpr"})
        risk_report = pd.concat(
            [
                risk_keep[["model_label", "roc_auc", "average_precision", "precision", "recall", "f1", "fpr"]],
                current_best,
            ],
            ignore_index=True,
        )
        display(risk_report)

        risk_long = risk_report.melt(
            id_vars=["model_label"],
            value_vars=["precision", "recall", "f1", "fpr"],
            var_name="metric",
            value_name="value",
        )
        risk_long["metric"] = risk_long["metric"].replace(
            {
                "precision": "정밀도",
                "precision": "Precision",
                "recall": "Recall",
                "f1": "F1",
                "fpr": "FPR",
            }
        )
        fig = px.bar(
            risk_long,
            x="metric",
            y="value",
            color="model_label",
            barmode="group",
            text=risk_long["value"].round(3),
            color_discrete_sequence=[COLORS["gray"], COLORS["teal"], COLORS["orange"], COLORS["blue"]],
            title="Risk 대표 후보 성능 비교 (Holdout)",
        )
        tidy(fig).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()
        """
    ),
    md(
        """
        ## 5. Leadtime 비교: 최종 판단값이 아니라 참고 신호

        leadtime은 “정확한 고장 시각 예측”이 아니라 priority에 들어가는 시간 근접성 참고 신호다.
        보고용 비교에서는 서로 의미가 너무 다른 binary redesign은 제외하고, bucket 설계와 최종 개선을 보여주는 후보만 남긴다.

        - `Original 4-bucket`: 더 세분화했지만 성능이 낮았다.
        - `Base 3-bucket`: 단순한 3-bucket 기준선이다.
        - `Official promoted 3-bucket`: macro/weighted F1이 소폭 개선되었다.
        - `Current-best leadtime`: 최종 current-best에서 accuracy, F1, bucket MAE가 개선되었다.
        """
    ),
    code(
        r"""
        lead_exp = data["leadtime_experiment"].copy()
        lead_keep = lead_exp[
            ((lead_exp["source"].eq("bucket_redesign")) & (lead_exp["experiment_name"].eq("bucket_redesign::original_4bucket")))
            | ((lead_exp["source"].eq("base_3bucket")) & (lead_exp["experiment_name"].eq("base_3bucket")))
            | ((lead_exp["source"].eq("official_promoted")) & (lead_exp["experiment_name"].eq("official_promoted")))
        ].copy()
        lead_keep["model_label"] = lead_keep["source"].map(
            {
                "bucket_redesign": "Original 4-bucket",
                "base_3bucket": "Base 3-bucket",
                "official_promoted": "Official promoted 3-bucket",
            }
        )

        best_lead_values = best[
            (best["model"].eq("best_leadtime"))
            & best["metric"].isin(["accuracy", "macro_f1", "weighted_f1", "top2_accuracy", "bucket_distance_mae"])
        ].set_index("metric")["value"].to_dict()
        current_lead = pd.DataFrame(
            [
                {
                    "model_label": "Current-best Leadtime",
                    "accuracy": best_lead_values["accuracy"],
                    "macro_f1": best_lead_values["macro_f1"],
                    "weighted_f1": best_lead_values["weighted_f1"],
                    "top2_accuracy": best_lead_values["top2_accuracy"],
                    "bucket_distance_mae": best_lead_values["bucket_distance_mae"],
                    "row_count": 86,
                }
            ]
        )
        lead_report = pd.concat(
            [
                lead_keep[["model_label", "row_count", "accuracy", "macro_f1", "weighted_f1", "top2_accuracy", "bucket_distance_mae"]],
                current_lead,
            ],
            ignore_index=True,
        )
        display(lead_report)

        lead_long = lead_report.melt(
            id_vars=["model_label"],
            value_vars=["accuracy", "macro_f1", "weighted_f1", "top2_accuracy", "bucket_distance_mae"],
            var_name="metric",
            value_name="value",
        )
        lead_long["metric"] = lead_long["metric"].replace(
            {
                "accuracy": "Accuracy",
                "macro_f1": "Macro F1",
                "weighted_f1": "Weighted F1",
                "top2_accuracy": "Top-2 Acc.",
                "bucket_distance_mae": "Bucket MAE",
            }
        )
        fig = px.bar(
            lead_long,
            x="metric",
            y="value",
            color="model_label",
            barmode="group",
            text=lead_long["value"].round(3),
            color_discrete_sequence=[COLORS["gray"], COLORS["orange"], COLORS["teal"], COLORS["green"]],
            title="Leadtime Bucket/모델 성능 비교 (Holdout)",
        )
        tidy(fig).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()
        """
    ),
    md(
        """
        ## 6. Priority LGBM을 최종 baseline으로 쓰지 않은 이유

        같은 holdout 조건에서 rule-based priority v2_threshold48이 LGBM priority-only 후보보다
        운영 action F1과 ranking 품질이 높았다.

        LGBM 후보는 precision/specificity는 높지만 recall 손실이 커서 실제 점검 우선순위에서 놓치는 구간이 많아졌다.
        """
    ),
    code(
        r"""
        cls = data["priority_lgbm_rule_class"].copy()
        cls_h = cls[
            cls["split"].eq("holdout")
            & cls["model_key"].isin(["rule_based", "lgbm_priority_only"])
        ].copy()
        cls_h["model_label"] = cls_h["model_key"].map(
            {
                "rule_based": "Rule-based priority",
                "lgbm_priority_only": "LGBM priority-only",
            }
        )
        cls_long = cls_h.melt(
            id_vars=["model_label"],
            value_vars=["action_precision", "action_recall", "action_f1", "action_specificity"],
            var_name="metric",
            value_name="value",
        )
        cls_long["metric"] = cls_long["metric"].replace(
            {
                "action_precision": "Precision",
                "action_recall": "Recall",
                "action_f1": "F1",
                "action_specificity": "Specificity",
            }
        )
        fig = px.bar(
            cls_long,
            x="metric",
            y="value",
            color="model_label",
            barmode="group",
            text=cls_long["value"].round(3),
            color_discrete_sequence=[COLORS["blue"], COLORS["orange"]],
            title="Priority Action 성능 비교 (Holdout): Rule 기반 vs LGBM",
        )
        tidy(fig).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()

        topk = data["priority_lgbm_rule_topk"].copy()
        ndcg = topk[
            topk["split"].eq("holdout")
            & topk["k_label"].eq("R")
            & topk["model_key"].isin(["rule_based", "lgbm_priority_only"])
        ].copy()
        ndcg["model_label"] = ndcg["model_key"].map(
            {
                "rule_based": "Rule-based priority",
                "lgbm_priority_only": "LGBM priority-only",
            }
        )
        fig = px.bar(
            ndcg,
            x="model_label",
            y="ndcg_graded",
            color="model_label",
            text=ndcg["ndcg_graded"].round(3),
            color_discrete_sequence=[COLORS["blue"], COLORS["orange"]],
            title="Priority Ranking 품질 비교 (Holdout): NDCG@R",
        )
        tidy(fig, height=380).update_layout(xaxis_title="", yaxis_title="NDCG@R", showlegend=False)
        fig.show()
        """
    ),
    md(
        """
        ## 7. 최종 M1 hybrid 채택 근거

        M1 specialist 단독은 최종 모델이 아니라 M1 전용 보조 evidence다.
        최종 hybrid는 current-best 대비 FPR을 크게 낮추고 precision을 높였다.
        fault-event recall은 세 후보 모두 0.875로 동일하게 유지되었다.
        """
    ),
    code(
        r"""
        m1 = data["m1_compare"].copy()
        holdout_row = m1[(m1["split"].eq("holdout")) & (m1["metric_scope"].eq("row"))].copy()
        holdout_event = m1[(m1["split"].eq("holdout")) & (m1["metric_scope"].eq("fault_event"))].copy()
        name_map = {
            "current_best_priority": "Current-best",
            "m1_specialist_priority": "M1 specialist",
            "m1_hybrid_priority": "Final hybrid",
        }
        holdout_row["policy_label"] = holdout_row["policy"].map(name_map)
        holdout_event["policy_label"] = holdout_event["policy"].map(name_map)

        final_table = holdout_row[
            ["policy_label", "row_count", "precision", "recall", "false_positive_rate", "tp", "fp", "fn", "tn"]
        ].rename(columns={"false_positive_rate": "FPR"})
        display(final_table)

        m1_long = holdout_row.melt(
            id_vars=["policy_label"],
            value_vars=["precision", "recall", "false_positive_rate"],
            var_name="metric",
            value_name="value",
        )
        m1_long["metric"] = m1_long["metric"].replace(
            {"precision": "Precision", "recall": "Recall", "false_positive_rate": "FPR"}
        )
        fig = px.bar(
            m1_long,
            x="metric",
            y="value",
            color="policy_label",
            barmode="group",
            text=m1_long["value"].round(3),
            color_discrete_sequence=[COLORS["gray"], COLORS["orange"], COLORS["green"]],
            title="최종 M1 Row 성능 비교 (Holdout)",
        )
        tidy(fig).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()

        fig = px.bar(
            holdout_event,
            x="policy_label",
            y="fault_event_recall",
            color="policy_label",
            text=holdout_event["fault_event_recall"].round(3),
            color_discrete_sequence=[COLORS["gray"], COLORS["orange"], COLORS["green"]],
            title="최종 M1 Fault-event 재현율 비교 (Holdout)",
        )
        tidy(fig, height=380).update_layout(xaxis_title="", yaxis_title="event recall", showlegend=False)
        fig.show()
        """
    ),
    md(
        """
        ## 8. 최종 active policy 해석

        최종 agent contract에서 주 정책은 `priority_high_or_urgent`와 `risk_high_or_critical`이다.
        M1 specialist와 anomaly는 단독 결론이 아니라 review/evidence 역할로 남긴다.
        """
    ),
    code(
        r"""
        abl = data["ablation"].copy()
        role_map = {
            "risk_high_or_critical": "Risk primary",
            "priority_high_or_urgent": "Priority primary",
            "m1_specialist_high_or_urgent": "M1 evidence",
            "anomaly_or_risk_high": "Broad review",
            "official_anomaly_evidence_event": "Anomaly evidence",
        }
        order = ["Risk primary", "Priority primary", "M1 evidence", "Anomaly evidence", "Broad review"]
        abl["role"] = pd.Categorical(abl["variant"].map(role_map), categories=order, ordered=True)
        abl = abl.sort_values("role")
        display(abl[["role", "variant", "precision", "recall", "false_positive_rate", "tp", "fp", "fn", "tn"]])

        abl_long = abl.melt(
            id_vars=["role"],
            value_vars=["precision", "recall", "false_positive_rate"],
            var_name="metric",
            value_name="value",
        )
        abl_long["metric"] = abl_long["metric"].replace(
            {"precision": "Precision", "recall": "Recall", "false_positive_rate": "FPR"}
        )
        fig = px.bar(
            abl_long,
            x="role",
            y="value",
            color="metric",
            barmode="group",
            text=abl_long["value"].round(3),
            color_discrete_sequence=[COLORS["blue"], COLORS["green"], COLORS["red"]],
            title="최종 Active Policy Ablation 비교",
        )
        tidy(fig).update_layout(xaxis_title="", yaxis_title="metric value")
        fig.show()
        """
    ),
    md(
        """
        ## 9. 최종 보고 문장

        최종본은 M1 specialist 단독 모델이 아니다. 기존 current-best risk/leadtime/priority 체인을 운영 baseline으로 유지하고,
        M1 specialist gate를 병렬 evidence로 붙여 priority score에 35% 반영한 conservative hybrid다.

        이 선택은 다음 사실에 기반한다.

        - anomaly는 정상 분포 이탈 evidence로 유용하지만 단독 알람 정책으로는 recall/FPR trade-off가 크다.
        - current-best risk는 이전 risk 후보보다 precision, F1, FPR이 명확히 개선되었다.
        - current-best leadtime은 기존 3-bucket promoted 후보보다 accuracy/F1/bucket MAE가 개선되었다.
        - priority LGBM 단독 후보는 rule-based priority보다 holdout action F1과 NDCG@R이 낮아 운영 baseline을 대체하지 못했다.
        - M1 specialist 단독은 M1 관점의 보조 근거를 제공하지만 단독 채택 성능은 부족했다.
        - 최종 hybrid는 M1 holdout에서 current-best 대비 precision을 높이고 FPR을 낮췄으며, fault-event recall은 유지했다.

        따라서 최종 agent contract는 `priority_score`, `priority_level`, `review_required`, `review_reasons`를 함께 제공하는 점검 우선순위 도구로 해석해야 한다.
        """
    ),
    md(
        """
        ## 10. 보고 시 반드시 붙일 고려사항

        - M1 holdout event 수는 8개로 작다. event recall은 방향성 근거로 보되 과대 해석하지 않는다.
        - label은 실제 고장 발생 시각이 아니라 event/proxy 성격이 있다.
        - pseudo-clean normal은 현장 완전 정상 보장이 아니다.
        - row reconciliation 기준 canonical 1252개와 현재 agent card 1252개가 모두 일치하며, final card 누락은 0개다.
        - priority score는 자동 정비 지시가 아니라 사람이 먼저 볼 대상을 정렬하는 운영 신호다.
        """
    ),
]

OUT.parent.mkdir(parents=True, exist_ok=True)
for idx, cell in enumerate(nb.cells):
    cell["id"] = f"cell-{idx:03d}"
OUT.write_text(nbf.writes(nb), encoding="utf-8", newline="\n")
print(f"Wrote {OUT}")
