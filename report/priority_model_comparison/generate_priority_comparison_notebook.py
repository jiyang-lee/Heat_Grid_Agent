from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report" / "priority_model_comparison"
NOTEBOOK_PATH = REPORT_DIR / "priority_lgbm_rule_hybrid_report.ipynb"


def md(text: str):
    return nbf.v4.new_markdown_cell(dedent(text).strip())


def code(text: str):
    return nbf.v4.new_code_cell(dedent(text).strip())


def build_notebook():
    nb = nbf.v4.new_notebook()
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "pygments_lexer": "ipython3",
        },
    }

    nb.cells = [
        md(
            """
            # Priority 모델 비교 및 Hybrid 가능성 검토

            이 노트북은 현재 공식 `Rule-based priority_engine_v2_threshold48` 모델과 팀원 `LGBM priority regression` 모델을 같은 데이터셋 위에서 비교하고, 두 모델을 단순 결합했을 때 실제로 성능 개선이 가능한지 검토한다.

            결론부터 말하면, 팀원 산출물은 **두 패키지가 맞다.** 하나는 priority LGBM 회귀 단독 패키지이고, 다른 하나는 anomaly/risk/leadtime 예측 모델과 priority LGBM 회귀를 합친 통합 패키지다. 다만 두 패키지 안의 최종 `lightgbm_priority_model.joblib`은 같은 파일이다.

            현재 공식 산출물 기준에서는 **Rule-based 모델을 공식 유지**하는 것이 맞다. LGBM은 train 구간에서는 일부 지표가 좋지만 validation/holdout에서 일반화가 약하고, 특히 운영상 중요한 `3일 이내 장애 리드타임` recall이 크게 낮다. 따라서 LGBM은 교체용 메인 모델보다 `shadow score`, `보조 ranking`, `model disagreement flag`로 쓰는 것이 안전하다.
            """
        ),
        md(
            """
            ## 분석 기준

            - 비교 데이터: `data/processed/ml_priority/priority_engine_scores_tuned.csv`
            - 라벨 조인: `data/processed/ml_features/trainable_windows.csv`
            - 실제 target score:
              - normal = 0
              - 3-7d = 33
              - 1-3d = 66
              - 0-24h = 100
            - 운영 액션 정의: `predicted high/urgent`가 `실제 3일 이내 장애 리드타임(0-24h 또는 1-3d)`을 포착하는지 평가
            - 결합 실험: `blend = w * rule_score + (1-w) * lgbm_score`
            """
        ),
        code(
            r"""
            from pathlib import Path
            import numpy as np
            import pandas as pd
            import plotly.express as px
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            from IPython.display import HTML, display
            from sklearn.metrics import mean_absolute_error, confusion_matrix
            from scipy.stats import spearmanr

            ROOT = Path.cwd()
            REPORT_DIR = ROOT / "report" / "priority_model_comparison"
            DATASET_PATH = REPORT_DIR / "priority_lgbm_vs_rule_dataset.csv"
            REGRESSION_PATH = REPORT_DIR / "priority_lgbm_vs_rule_regression_metrics.csv"
            CLASSIFICATION_PATH = REPORT_DIR / "priority_lgbm_vs_rule_classification_metrics.csv"
            TOPK_PATH = REPORT_DIR / "priority_lgbm_vs_rule_topk_metrics.csv"
            MODEL_FILES_PATH = REPORT_DIR / "priority_lgbm_vs_rule_model_files.csv"
            PACKAGE_SCOPE_PATH = REPORT_DIR / "priority_lgbm_vs_rule_package_scope.csv"
            UPSTREAM_HASH_PATH = REPORT_DIR / "priority_lgbm_vs_rule_upstream_hash_check.csv"

            FONT = "Malgun Gothic, Apple SD Gothic Neo, Noto Sans CJK KR, Arial, sans-serif"
            BUCKET_ORDER = ["normal", "3-7d", "1-3d", "0-24h"]
            LEVEL_ORDER = ["low", "medium", "high", "urgent"]

            def show_fig(fig):
                fig.update_layout(
                    template="plotly_white",
                    font=dict(family=FONT, size=13),
                    margin=dict(l=50, r=30, t=70, b=55),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                display(HTML(fig.to_html(full_html=False, include_plotlyjs="cdn")))

            df = pd.read_csv(DATASET_PATH)
            reg = pd.read_csv(REGRESSION_PATH)
            cls = pd.read_csv(CLASSIFICATION_PATH)
            topk = pd.read_csv(TOPK_PATH)
            model_files = pd.read_csv(MODEL_FILES_PATH)
            package_scope = pd.read_csv(PACKAGE_SCOPE_PATH)
            upstream_hash = pd.read_csv(UPSTREAM_HASH_PATH)

            rename_model = {
                "Rule-based v2_threshold48": "Rule-based",
                "LGBM priority-only package": "LGBM",
                "LGBM prediction+priority package": "LGBM bundled",
            }
            for frame in [reg, cls, topk]:
                frame["model_short"] = frame["model"].map(rename_model).fillna(frame["model"])

            df["plot_bucket"] = pd.Categorical(df["true_bucket"], BUCKET_ORDER, ordered=True)
            df["rule_minus_lgbm"] = df["rule_based_score"] - df["lgbm_priority_only_score"]
            df["abs_score_gap"] = df["rule_minus_lgbm"].abs()

            print(f"rows: {len(df):,}")
            print(df["split_time_based"].value_counts().to_string())
            print()
            print(df["true_bucket"].value_counts().reindex(BUCKET_ORDER).to_string())
            """
        ),
        md(
            """
            ## 1. 패키지 구조와 모델 파일 확인

            팀원 폴더에는 패키지가 두 개 있는 것이 맞다.

            - `heatgrid_priority_model_2026-06-26`: priority LGBM 회귀 모델만 포함
            - `heatgrid_prediction_priority_models_2026-06-26`: anomaly/risk/leadtime 예측 모델과 priority LGBM 회귀 모델을 함께 포함

            다만 두 패키지 안의 최종 priority 회귀 estimator인 `lightgbm_priority_model.joblib`은 SHA256 기준으로 같은 파일이다. 또한 통합 패키지에 들어 있는 upstream anomaly/risk/leadtime 모델은 현재 공식 `model_handoff/heatgrid_ml_models_2026-06-25` 모델과 SHA256 기준으로 동일하다.
            """
        ),
        code(
            r"""
            display(package_scope[[
                "package_key", "package_role", "contains_anomaly_model", "contains_risk_model",
                "contains_leadtime_model", "contains_priority_lgbm",
                "priority_lgbm_same_as_other_package", "upstream_models_match_official_handoff"
            ]])

            display(upstream_hash[[
                "upstream_model", "matches_official_model_handoff", "bundle_sha256", "official_sha256"
            ]])

            display(model_files[[
                "model_key", "model_version", "model_type", "best_iteration",
                "n_train_metadata", "n_holdout_metadata", "sha256"
            ]])

            lgbm_hashes = model_files["sha256"].unique()
            print(f"LGBM joblib unique hashes: {len(lgbm_hashes)}")
            print(f"두 LGBM 패키지 예측 최대 차이: {(df['lgbm_priority_only_score'] - df['lgbm_prediction_bundle_score']).abs().max():.6f}")
            """
        ),
        md("## 2. 비교 데이터 분포"),
        code(
            r"""
            split_counts = df.groupby(["split_time_based", "true_bucket"]).size().reset_index(name="count")
            split_counts["true_bucket"] = pd.Categorical(split_counts["true_bucket"], BUCKET_ORDER, ordered=True)
            fig = px.bar(
                split_counts.sort_values("true_bucket"),
                x="split_time_based",
                y="count",
                color="true_bucket",
                barmode="stack",
                labels={"split_time_based": "split", "count": "윈도우 수", "true_bucket": "실제 버킷"},
                title="Split별 실제 target bucket 분포",
            )
            show_fig(fig)
            """
        ),
        md(
            """
            ## 3. 점수 분포 비교

            Rule-based는 장애 임박 버킷으로 갈수록 점수가 비교적 일관되게 상승한다. LGBM은 전체적으로 더 보수적인 점수 분포를 보이며, holdout에서 high/urgent 구간으로 올리는 샘플 수가 적다.
            """
        ),
        code(
            r"""
            long_scores = pd.concat(
                [
                    df.assign(model="Rule-based", score=df["rule_based_score"]),
                    df.assign(model="LGBM", score=df["lgbm_priority_only_score"]),
                ],
                ignore_index=True,
            )
            long_scores["true_bucket"] = pd.Categorical(long_scores["true_bucket"], BUCKET_ORDER, ordered=True)

            fig = px.violin(
                long_scores,
                x="true_bucket",
                y="score",
                color="model",
                box=True,
                points=False,
                labels={"true_bucket": "실제 리드타임 버킷", "score": "priority score", "model": "모델"},
                title="실제 버킷별 priority score 분포",
            )
            show_fig(fig)
            """
        ),
        code(
            r"""
            fig = px.scatter(
                df,
                x="rule_based_score",
                y="lgbm_priority_only_score",
                color="true_bucket",
                symbol="split_time_based",
                category_orders={"true_bucket": BUCKET_ORDER},
                opacity=0.72,
                hover_data=["manufacturer", "substation_id", "window_start", "target_score", "rule_based_level", "lgbm_priority_only_level"],
                labels={
                    "rule_based_score": "Rule-based score",
                    "lgbm_priority_only_score": "LGBM score",
                    "true_bucket": "실제 버킷",
                    "split_time_based": "split",
                },
                title="Rule-based와 LGBM priority score 관계",
            )
            fig.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines", line=dict(color="black", dash="dash"), name="y=x"))
            show_fig(fig)
            """
        ),
        md(
            """
            ## 4. 회귀/순위 지표

            전체 데이터 기준 MAE는 LGBM이 약간 낮지만, holdout에서는 Rule-based가 더 낮은 MAE/RMSE와 더 높은 상관을 보인다. 운영에서는 holdout 일반화가 더 중요하므로 이 차이가 핵심 근거다.
            """
        ),
        code(
            r"""
            reg_focus = reg[
                reg["model_key"].isin(["rule_based", "lgbm_priority_only"]) &
                reg["split"].isin(["all", "train", "validation", "holdout"])
            ][["split", "model_short", "n", "mae", "rmse", "r2", "spearman"]]
            display(reg_focus)

            metric_long = reg_focus.melt(
                id_vars=["split", "model_short"],
                value_vars=["mae", "rmse", "spearman"],
                var_name="metric",
                value_name="value",
            )
            fig = px.bar(
                metric_long,
                x="split",
                y="value",
                color="model_short",
                facet_col="metric",
                barmode="group",
                labels={"split": "split", "value": "값", "model_short": "모델", "metric": "지표"},
                title="회귀/순위 상관 지표 비교",
            )
            show_fig(fig)
            """
        ),
        md(
            """
            ## 5. 운영 액션 지표

            운영상 중요한 질문은 `high/urgent로 올린 대상이 실제 3일 이내 장애 리드타임을 얼마나 포착하는가`이다. Holdout 기준 Rule-based는 recall 0.7103, LGBM은 0.3271로 차이가 크다. LGBM은 더 보수적이라 specificity는 약간 높지만, 장애 임박 건을 너무 많이 놓친다.
            """
        ),
        code(
            r"""
            cls_focus = cls[
                cls["model_key"].isin(["rule_based", "lgbm_priority_only"]) &
                cls["split"].isin(["all", "train", "validation", "holdout"])
            ][[
                "split", "model_short", "level_accuracy", "level_macro_f1",
                "action_precision", "action_recall", "action_f1", "action_specificity", "action_rate"
            ]]
            display(cls_focus)

            cls_long = cls_focus.melt(
                id_vars=["split", "model_short"],
                value_vars=["action_precision", "action_recall", "action_f1", "action_specificity", "action_rate"],
                var_name="metric",
                value_name="value",
            )
            fig = px.bar(
                cls_long,
                x="split",
                y="value",
                color="model_short",
                facet_col="metric",
                barmode="group",
                labels={"split": "split", "value": "값", "model_short": "모델", "metric": "지표"},
                title="High/Urgent 운영 액션 지표",
            )
            fig.update_yaxes(range=[0, 1.03])
            show_fig(fig)
            """
        ),
        md("## 6. Holdout Top-K 증거"),
        code(
            r"""
            holdout_topk = topk[
                topk["model_key"].isin(["rule_based", "lgbm_priority_only"]) &
                topk["split"].eq("holdout") &
                topk["k_label"].isin(["10", "20", "50", "100", "R"])
            ][["model_short", "k_label", "pre_fault_count", "precision_pre_fault", "recall_pre_fault", "ndcg_graded"]]
            display(holdout_topk)

            fig = make_subplots(rows=1, cols=3, subplot_titles=("Precision@K", "Recall@K", "Graded NDCG@K"))
            for model, group in holdout_topk.groupby("model_short"):
                x = group["k_label"].astype(str)
                fig.add_trace(go.Scatter(x=x, y=group["precision_pre_fault"], mode="lines+markers", name=model), row=1, col=1)
                fig.add_trace(go.Scatter(x=x, y=group["recall_pre_fault"], mode="lines+markers", name=model, showlegend=False), row=1, col=2)
                fig.add_trace(go.Scatter(x=x, y=group["ndcg_graded"], mode="lines+markers", name=model, showlegend=False), row=1, col=3)
            fig.update_layout(title="Holdout Top-K pre_fault 포착 성능")
            fig.update_yaxes(range=[0, 1.03])
            show_fig(fig)
            """
        ),
        md(
            """
            ## 7. 단순 결합 실험

            아래는 `blend = w * rule_score + (1-w) * lgbm_score`로 단순 가중 평균을 만든 결과다. Validation 기준으로 비율을 고르면 대부분 Rule-based 100% 또는 Rule-based에 매우 가까운 조합이 선택된다. Holdout에서도 LGBM 비중이 커질수록 recall과 Top-K 포착률이 악화된다.
            """
        ),
        code(
            r"""
            def action_metrics(part, score, threshold=48.0):
                y_true = (part["target_score"] >= 66).to_numpy()
                y_pred = np.asarray(score) >= threshold
                tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[False, True]).ravel()
                precision = tp / (tp + fp) if tp + fp else np.nan
                recall = tp / (tp + fn) if tp + fn else np.nan
                f1 = 2 * precision * recall / (precision + recall) if precision + recall else np.nan
                specificity = tn / (tn + fp) if tn + fp else np.nan
                return precision, recall, f1, specificity, float(y_pred.mean())

            def ndcg_at_k(rel, scores, k):
                k = min(k, len(rel))
                order = np.argsort(scores)[::-1][:k]
                ideal = np.argsort(rel)[::-1][:k]
                discounts = 1 / np.log2(np.arange(2, k + 2))
                dcg = float(np.sum(rel[order] * discounts))
                idcg = float(np.sum(rel[ideal] * discounts))
                return dcg / idcg if idcg > 0 else np.nan

            def topk_metrics(part, score, k=100):
                y = part["is_pre_fault"].astype(bool).to_numpy()
                rel = (part["target_score"].astype(float) / 100).to_numpy()
                order = np.argsort(score)[::-1][:min(k, len(part))]
                hits = int(y[order].sum())
                return hits / min(k, len(part)), hits / max(1, int(y.sum())), ndcg_at_k(rel, score, k)

            blend_rows = []
            for w in np.linspace(0, 1, 101):
                score = w * df["rule_based_score"] + (1 - w) * df["lgbm_priority_only_score"]
                for split in ["train", "validation", "holdout", "all"]:
                    part = df if split == "all" else df[df["split_time_based"] == split]
                    part_score = score.loc[part.index].to_numpy()
                    precision, recall, f1, specificity, action_rate = action_metrics(part, part_score, threshold=48)
                    p100, r100, ndcg100 = topk_metrics(part, part_score, k=100)
                    y = part["target_score"].astype(float).to_numpy()
                    blend_rows.append({
                        "w_rule": w,
                        "w_lgbm": 1 - w,
                        "split": split,
                        "mae": mean_absolute_error(y, part_score),
                        "rmse": float(np.sqrt(np.mean((y - part_score) ** 2))),
                        "spearman": float(spearmanr(y, part_score).statistic),
                        "precision": precision,
                        "recall": recall,
                        "f1": f1,
                        "specificity": specificity,
                        "action_rate": action_rate,
                        "p@100": p100,
                        "r@100": r100,
                        "ndcg@100": ndcg100,
                    })
            blend = pd.DataFrame(blend_rows)

            fixed = blend[
                blend["split"].eq("holdout") &
                blend["w_rule"].round(2).isin([0, 0.25, 0.5, 0.75, 0.8, 0.9, 0.95, 1.0])
            ].copy()
            fixed["candidate"] = fixed["w_rule"].map(lambda x: "Rule-based" if x == 1 else ("LGBM" if x == 0 else f"Rule {x:.2f} + LGBM {1-x:.2f}"))
            display(fixed[["candidate", "mae", "rmse", "spearman", "precision", "recall", "f1", "specificity", "action_rate", "p@100", "r@100", "ndcg@100"]])

            holdout_blend = blend[blend["split"].eq("holdout")].copy()
            blend_long = holdout_blend.melt(
                id_vars=["w_rule"],
                value_vars=["mae", "recall", "f1", "r@100", "ndcg@100"],
                var_name="metric",
                value_name="value",
            )
            fig = px.line(
                blend_long,
                x="w_rule",
                y="value",
                color="metric",
                facet_col="metric",
                facet_col_wrap=3,
                markers=True,
                labels={"w_rule": "Rule-based 가중치", "value": "값", "metric": "지표"},
                title="Holdout 기준 단순 blend 비율별 성능",
            )
            show_fig(fig)
            """
        ),
        code(
            r"""
            selection_rows = []
            for metric, direction in [
                ("mae", "min"), ("rmse", "min"), ("spearman", "max"),
                ("f1", "max"), ("recall", "max"), ("ndcg@100", "max"), ("r@100", "max")
            ]:
                val = blend[blend["split"].eq("validation")]
                idx = val[metric].idxmin() if direction == "min" else val[metric].idxmax()
                selected = val.loc[idx]
                holdout = blend[(blend["split"].eq("holdout")) & (blend["w_rule"].eq(selected["w_rule"]))].iloc[0]
                selection_rows.append({
                    "selected_by_validation": metric,
                    "direction": direction,
                    "w_rule": selected["w_rule"],
                    "w_lgbm": selected["w_lgbm"],
                    "holdout_mae": holdout["mae"],
                    "holdout_recall": holdout["recall"],
                    "holdout_f1": holdout["f1"],
                    "holdout_r@100": holdout["r@100"],
                    "holdout_ndcg@100": holdout["ndcg@100"],
                })
            selection = pd.DataFrame(selection_rows)
            display(selection)

            fig = px.bar(
                selection,
                x="selected_by_validation",
                y=["w_rule", "w_lgbm"],
                barmode="stack",
                labels={"selected_by_validation": "validation 선택 기준", "value": "가중치", "variable": "모델"},
                title="Validation 기준 최적 blend 가중치",
            )
            show_fig(fig)
            """
        ),
        md(
            """
            ## 8. 결론

            1. 팀원 산출물은 두 패키지가 맞다. 하나는 priority LGBM 회귀 단독 패키지이고, 다른 하나는 예측 체인과 priority LGBM 회귀를 합친 통합 패키지다.
            2. 두 패키지의 최종 priority LGBM 회귀 파일은 SHA256 기준 동일하다. 따라서 priority score 비교에서는 두 패키지 간 LGBM 결과 차이가 없다.
            3. 통합 패키지의 anomaly/risk/leadtime 모델은 현재 공식 `model_handoff` 모델과 SHA256 기준 동일하다.
            4. 현재 공식 산출물 기준으로는 Rule-based가 holdout에서 더 안정적이다.
            5. LGBM은 더 보수적으로 high/urgent를 예측해 specificity는 일부 좋아지지만, recall이 크게 낮아 장애 임박 건을 많이 놓친다.
            6. 단순 weighted average ensemble은 유의미한 개선을 만들지 못했다. validation 기준 최적 가중치도 대부분 Rule-based 100% 또는 Rule-based에 매우 가까운 조합이다.
            7. 따라서 운영 모델은 `priority_engine_v2_threshold48`을 유지하고, LGBM은 아래처럼 보조 신호로 쓰는 것이 안전하다.

            ```text
            final_priority_score = rule_based_score

            추가 제공:
            - lgbm_priority_score
            - lgbm_priority_level
            - rule_lgbm_agreement_flag
            - review_hint

            운영 규칙:
            - rule high/urgent는 LGBM이 낮아도 강등하지 않는다.
            - rule medium인데 LGBM이 매우 높으면 검토 후보로 표시한다.
            - rule과 LGBM이 모두 높으면 confidence 높은 우선 점검 대상으로 표시한다.
            ```
            """
        ),
    ]
    return nb


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    nb = build_notebook()
    client = NotebookClient(nb, timeout=180, kernel_name="python3")
    client.execute()
    nbf.write(nb, NOTEBOOK_PATH)
    print(NOTEBOOK_PATH)


if __name__ == "__main__":
    main()
