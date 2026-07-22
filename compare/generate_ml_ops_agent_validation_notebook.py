from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
OUT = PACKAGE_ROOT / "compare" / "ml_ops_agent_validation_ko.ipynb"


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
        # HeatGrid ML 성능·운영 우선순위·Agent 구성 검증

        이 노트북은 발표자료의 기존 **운영 우선순위 검증**과 **Agent 구성**을 대체할 수 있도록,
        다음 세 페이지의 근거를 한글로 정리한 실행형 검증 자료다.

        1. **ML 성능 검증** — 후보 모델과 현재 활성 모델의 성능을 같은 계약 안에서 비교
        2. **운영 우선순위 검증** — Rule-based/LGBM 및 M1 hybrid 가중치·임계값 비교
        3. **Agent 구성** — 현재 코드의 LangGraph v2 9단계와 모델 역할 분리

        핵심 원칙은 세 가지다.

        - `artifacts/current_best`의 상위 프로젝트 성능과 현재 복원 artifact의 재검증 성능을 같은 값처럼 섞지 않는다.
        - holdout을 직접 최적화한 후보와 실제 활성 설정을 구분한다.
        - 서로 다른 window/label/split 계약의 결과는 보조 근거로만 사용한다.

        > 결론 요약: 상위 프로젝트에서는 Rule-based priority가 LGBM보다 일반화가 안정적이다.
        > 검증된 handoff Risk·Leadtime artifact를 복원해 내부 임시 재학습의 과적합 문제를 제거했다.
        > 복원 Risk holdout은 정밀도 85.7%, F1 51.1%, FPR 4.7%이며 Leadtime macro-F1은 69.3%, Top-2는 98.5%다.
        > 공식 Priority v4는 운영 시점에 알 수 있는 restored Risk와 pre-event만 사용한다.
        > v4 holdout은 정밀도 83.6%, 재현율 72.7%, F1 77.8%, FPR 10.4%, 이벤트 7/8이다.
        """
    ),
    md(
        """
        ## 0. 실행 환경과 근거 파일

        노트북은 `Heat_Grid_Beta` 저장소 또는 그 하위 경로에서 실행할 수 있다.
        모든 표와 차트는 로컬 CSV/JSON/소스 코드에서 다시 계산한다.
        """
    ),
    code(
        r"""
        import hashlib
        import json
        import re
        from pathlib import Path

        import numpy as np
        import pandas as pd
        import plotly.express as px
        import plotly.graph_objects as go
        import plotly.io as pio
        from IPython.display import Markdown, display

        pio.renderers.default = "plotly_mimetype"
        pd.set_option("display.max_columns", 80)
        pd.set_option("display.max_colwidth", 100)

        def find_repo_root() -> Path:
            cwd = Path.cwd().resolve()
            for candidate in [cwd, *cwd.parents]:
                if (
                    (candidate / "models/model_artifacts_metadata.json").exists()
                    and (candidate / "artifacts/current_best").exists()
                    and (candidate / "src/heatgrid_ops/agent/v2_models.py").exists()
                ):
                    return candidate
            raise FileNotFoundError("Heat_Grid_Beta 저장소 루트를 찾지 못했습니다.")

        REPO = find_repo_root()
        PROJECT3 = REPO.parent
        ART = REPO / "artifacts" / "current_best"
        REPORT = REPO / "output" / "reports"

        def read_csv(path: Path) -> pd.DataFrame:
            if not path.exists():
                raise FileNotFoundError(path)
            return pd.read_csv(path)

        def read_json(path: Path) -> dict:
            if not path.exists():
                raise FileNotFoundError(path)
            return json.loads(path.read_text(encoding="utf-8-sig"))

        def sha256(path: Path) -> str:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        def f1_score(precision: float, recall: float) -> float:
            return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

        COLORS = {
            "navy": "#173B8E",
            "blue": "#2D6CDF",
            "sky": "#69B9D1",
            "green": "#2DAA78",
            "orange": "#F28C45",
            "red": "#E53E3E",
            "purple": "#7A5AF8",
            "gray": "#687386",
        }

        paths = {
            "upstream_best_comparison": ART / "reports/best_pipeline_comparison.csv",
            "upstream_ops": ART / "reports/operational/operational_policy_comparison.csv",
            "upstream_ranking": ART / "reports/priority/priority_ranking_comparison.csv",
            "priority_lgbm_rule": ART / "experiment_traces/priority_compare/priority_lgbm_vs_rule_classification_metrics.csv",
            "priority_lgbm_topk": ART / "experiment_traces/priority_compare/priority_lgbm_vs_rule_topk_metrics.csv",
            "anomaly_metrics": REPO / "output/anomaly_metrics.csv",
            "local_risk": REPORT / "internal_current_best_risk_metrics.csv",
            "local_leadtime": REPORT / "internal_current_best_leadtime_metrics.csv",
            "active_priority": REPORT / "m1_specialist_vs_current_best_comparison.csv",
            "evidence_gate_sweep": REPORT / "m1_risk_pre_event_gate_threshold_sweep.csv",
            "hybrid_selection": REPORT / "hybrid_weight_selection_summary.csv",
            "hybrid_selected": REPORT / "hybrid_selected_weight_comparison.csv",
            "hybrid_delta": REPORT / "hybrid_065_vs_072_metric_delta.csv",
            "active_metadata": REPORT / "m1_specialist_metadata.json",
            "artifact_metadata": REPO / "models/model_artifacts_metadata.json",
            "risk_metadata": REPO / "models/risk/risk_model_best_metadata.json",
            "leadtime_metadata": REPO / "models/leadtime/leadtime_model_best_metadata.json",
            "priority_metadata": REPO / "models/priority/priority_engine_best_metadata.json",
            "grid_broad": PROJECT3 / "3rd_model/output/reports/grid_beststyle_vs_best_holdout_comparison.csv",
            "grid_m1": PROJECT3 / "3rd_model_M1/output/reports/grid_beststyle_vs_best_holdout_comparison.csv",
            "da_rebaseline": PROJECT3 / "da/reports/m1_rebaseline_experiment_v2/m1_rebaseline_recommended_strategy.csv",
            "xai_mock": PROJECT3 / "xai4heat_mock_experiment/reports/synthetic_performance_metrics.csv",
            "settings": REPO / "simulator/versions/v2_postgres_react_ops/backend/settings.py",
            "stages": REPO / "src/heatgrid_ops/agent/v2_models.py",
            "scenario_data": REPO / "frontend/src/scenario/scenarioData.ts",
            "agent_observations": REPO / "compare/agent_cycle_observations_20260721.csv",
        }

        required = pd.DataFrame(
            [{"근거": name, "경로": str(path), "존재": path.exists()} for name, path in paths.items()]
        )
        display(required)
        if not required["존재"].all():
            missing = required.loc[~required["존재"], "경로"].tolist()
            raise FileNotFoundError(f"필수 근거 파일 누락: {missing}")
        """
    ),
    code(
        r"""
        source_catalog = pd.DataFrame(
            [
                ["Heat_Grid_Beta/output", "현재 활성 산출물", "최우선", "검증 artifact 재현 성능·배포 메타데이터·Agent Card"],
                ["Heat_Grid_Beta/artifacts/current_best", "상위 current-best 보존본", "높음", "이전 후보 대비 모델 선택 근거; 현재 복원 artifact 재검증과 분리"],
                ["HeatGrid_Agent/best", "상위 파이프라인 원본", "높음", "운영 정책 10개 이벤트·25.6h 결과의 원출처"],
                ["Heat_Grid_Agent_agent_mlmodel", "통합/복제 패키지", "중간", "동일 artifact가 많아 독립 반복실험으로 계산하지 않음"],
                ["m1_specialist_handoff", "인수인계 복제본", "중간", "현재 output과 SHA256 중복 여부 확인용"],
                ["3rd_model / 3rd_model_M1", "Grid raw/best-style 도전자", "중간-높음", "입력 계약이 다른 challenger 비교; 동일 모델 단독 비교 아님"],
                ["da", "M1 rolling/rebaseline 실험", "중간", "25.6h 등 운영 후보의 출처; label 기반 제외 규칙과 계약 차이 주의"],
                ["Project3_Grid_ML / 3rd_project", "초기/전문가 실험", "보조", "후속 3rd_model 비교와 M1 gate package에 흡수됨"],
                ["xai4heat_mock_experiment", "합성 스트레스 테스트", "보조", "도메인 이동 시 오경보 붕괴 확인; 승격 성능으로 사용 금지"],
            ],
            columns=["폴더", "역할", "근거 등급", "사용 원칙"],
        )
        display(source_catalog)

        duplicate_checks = []
        handoff_root = PROJECT3 / "m1_specialist_handoff"
        pairs = [
            (REPORT / "hybrid_weight_selection_summary.csv", handoff_root / "reports/hybrid_weight_selection_summary.csv"),
            (REPORT / "final_validation_report.md", handoff_root / "reports/final_validation_report.md"),
            (REPO / "output/agent_priority_card.csv", handoff_root / "agent_contract/agent_priority_card.csv"),
        ]
        for left, right in pairs:
            duplicate_checks.append(
                {
                    "현재 파일": left.name,
                    "인수인계 파일 존재": right.exists(),
                    "SHA256 동일": right.exists() and sha256(left) == sha256(right),
                }
            )
        display(pd.DataFrame(duplicate_checks))
        """
    ),
    md(
        """
        ## 1. 현재 활성 계약 확인

        발표 수치보다 먼저, 어떤 모델과 임계값이 실제 활성인지 확인한다.
        `artifacts/current_best`는 비교 근거 보존본이고, 현재 실행 모드는 로컬 M1 재학습이다.
        """
    ),
    code(
        r"""
        artifact_meta = read_json(paths["artifact_metadata"])
        risk_meta = read_json(paths["risk_metadata"])
        lead_meta = read_json(paths["leadtime_metadata"])
        priority_meta = read_json(paths["priority_metadata"])
        m1_meta = read_json(paths["active_metadata"])

        agent_card = read_csv(REPO / "output/agent_priority_card.csv")
        agent_card_copy = read_csv(REPO / "output/agent/m1_agent_priority_card.csv")
        parallel_card = read_csv(REPO / "output/agent/m1_specialist_parallel_agent_card.csv")

        active_contract = pd.DataFrame(
            [
                ["실행 모드", artifact_meta["source_mode"], "현재 local M1 재학습 산출물"],
                ["Risk", risk_meta["model_version"], f"{risk_meta['model_type']} / {risk_meta['feature_count']} features"],
                ["Leadtime", lead_meta["model_version"], f"{lead_meta['model_type']} / {lead_meta['feature_count']} features"],
                ["Priority body", priority_meta["engine_version"], "Rule 기반 risk + leadtime"],
                ["최종 Priority", m1_meta["official_priority_source"], "current-best 65% + M1 specialist 35%"],
                ["활성 level 임계값", f"high={m1_meta['m1_hybrid_thresholds']['high']}, urgent={m1_meta['m1_hybrid_thresholds']['urgent']}", "현재 Agent Card 생성 설정"],
            ],
            columns=["구성", "활성 값", "설명"],
        )
        display(active_contract)

        card_integrity = pd.DataFrame(
            [
                ["공식 Agent Card", len(agent_card), len(agent_card.columns), sha256(REPO / "output/agent_priority_card.csv")[:16]],
                ["공식 Card 사본", len(agent_card_copy), len(agent_card_copy.columns), sha256(REPO / "output/agent/m1_agent_priority_card.csv")[:16]],
                ["M1 specialist 병렬 Card", len(parallel_card), len(parallel_card.columns), sha256(REPO / "output/agent/m1_specialist_parallel_agent_card.csv")[:16]],
            ],
            columns=["파일 역할", "행", "열", "SHA256 앞 16자리"],
        )
        display(card_integrity)
        assert sha256(REPO / "output/agent_priority_card.csv") == sha256(REPO / "output/agent/m1_agent_priority_card.csv")
        """
    ),
    md(
        """
        ## PPT용 현재 모델 개별 성능 평가표

        아래 표는 서로 다른 문제를 한 점수로 합치지 않는다.

        - 이상탐지: 정상 이탈을 찾는 보조 근거
        - Risk: 사전고장 이진 분류
        - Leadtime: 고장까지 남은 시간 구간 분류
        - Priority: 운영자가 실제로 조치할 high/urgent 판정

        특히 화면의 `scenario-ml-result.v1` 세 점수는 `scenarioData.ts`에 고정된 시연값이다.
        학습 모델의 추론 로그가 아니므로 정확도·F1 평가 대상에 포함하지 않는다.
        """
    ),
    code(
        r"""
        PPT_TABLE_DIR = REPO / "compare" / "ppt_tables"
        PPT_TABLE_DIR.mkdir(parents=True, exist_ok=True)

        anomaly_names = {
            "iforest_policy": "Isolation Forest 정책",
            "mahalanobis_policy": "Mahalanobis 정책",
            "policy_and_point": "IF·Mahalanobis 결합",
            "strong_q99_and_point": "강한 q99 결합",
            "policy_and_criticality": "지속성 criticality 결합",
        }
        anomaly_eval = read_csv(paths["anomaly_metrics"])
        anomaly_table = anomaly_eval[
            anomaly_eval["split"].isin(["validation", "holdout"])
        ][
            [
                "method", "split", "row_count", "normal_count", "pre_fault_count",
                "precision", "recall", "f1", "false_positive_rate", "roc_auc",
                "average_precision",
            ]
        ].copy()
        anomaly_table["모델/정책"] = anomaly_table["method"].map(anomaly_names)
        anomaly_table["검증 구간"] = anomaly_table["split"].replace(
            {"validation": "검증", "holdout": "홀드아웃"}
        )
        anomaly_table["판정"] = np.where(
            anomaly_table["split"].eq("holdout"),
            "홀드아웃 참고; 보조 신호로만 사용",
            "분포 이동 취약; 독립 알람 사용 금지",
        )
        anomaly_table = anomaly_table[
            [
                "모델/정책", "검증 구간", "row_count", "normal_count", "pre_fault_count",
                "precision", "recall", "f1", "false_positive_rate", "roc_auc",
                "average_precision", "판정",
            ]
        ].rename(
            columns={
                "row_count": "표본 수", "normal_count": "정상", "pre_fault_count": "사전고장",
                "precision": "정밀도", "recall": "재현율", "f1": "F1",
                "false_positive_rate": "오경보율", "roc_auc": "ROC-AUC",
                "average_precision": "Average Precision",
            }
        )

        risk_eval = read_csv(paths["local_risk"])
        risk_table = risk_eval[
            [
                "split", "row_count", "normal_count", "pre_fault_count", "precision",
                "recall", "f1", "false_positive_rate", "roc_auc", "average_precision",
            ]
        ].copy()
        risk_table["검증 구간"] = risk_table["split"].replace(
            {"train": "학습", "validation": "검증", "holdout": "홀드아웃"}
        )
        risk_table["판정"] = risk_table["split"].map(
            {
                "train": "학습 적합값; 일반화 성능 아님",
                "validation": "FPR 5% cap 통과; recall 보완 필요",
                "holdout": "저오경보 복원; pre-event 결합 사용",
            }
        )
        risk_table.insert(0, "현재 모델", risk_meta["model_version"])
        risk_table = risk_table[
            [
                "현재 모델", "검증 구간", "row_count", "normal_count", "pre_fault_count",
                "precision", "recall", "f1", "false_positive_rate", "roc_auc",
                "average_precision", "판정",
            ]
        ].rename(
            columns={
                "row_count": "표본 수", "normal_count": "정상", "pre_fault_count": "사전고장",
                "precision": "정밀도", "recall": "재현율", "f1": "F1",
                "false_positive_rate": "오경보율", "roc_auc": "ROC-AUC",
                "average_precision": "Average Precision",
            }
        )

        lead_eval = read_csv(paths["local_leadtime"])
        leadtime_table = lead_eval.copy()
        leadtime_table["검증 구간"] = leadtime_table["split"].replace(
            {"train": "학습", "validation": "검증", "holdout": "홀드아웃"}
        )
        leadtime_table["판정"] = leadtime_table["split"].map(
            {
                "train": "학습 적합값; 일반화 성능 아님",
                "validation": "표본 26건; 추가 검증 필요",
                "holdout": "승격 후보; 외부검증 필요",
            }
        )
        leadtime_table.insert(0, "현재 모델", lead_meta["model_version"])
        leadtime_table = leadtime_table[
            [
                "현재 모델", "검증 구간", "row_count", "macro_f1", "weighted_f1",
                "top2_accuracy", "판정",
            ]
        ].rename(
            columns={
                "row_count": "표본 수", "macro_f1": "Macro-F1",
                "weighted_f1": "Weighted-F1", "top2_accuracy": "Top-2 정확도",
            }
        )

        active_priority_eval = read_csv(paths["active_priority"])
        priority_rows = active_priority_eval[
            active_priority_eval["split"].eq("holdout")
            & active_priority_eval["metric_scope"].eq("row")
        ][
            [
                "policy", "row_count", "precision", "recall",
                "false_positive_rate", "tp", "fp", "fn", "tn", "mean_score",
            ]
        ].copy()
        priority_events = active_priority_eval[
            active_priority_eval["split"].eq("holdout")
            & active_priority_eval["metric_scope"].eq("fault_event")
        ][["policy", "fault_events", "detected_fault_events", "fault_event_recall"]]
        priority_table = priority_rows.merge(priority_events, on="policy", how="left")
        priority_table["f1"] = [
            f1_score(p, r) for p, r in zip(priority_table["precision"], priority_table["recall"])
        ]
        priority_table["설정"] = priority_table["policy"].replace(
            {
                "current_best_priority": "현재 로컬 Rule body",
                "m1_specialist_priority": "M1 specialist 단독",
                "legacy_priority": "이전 공식 v1 0.65/0.35·82.5/95.0",
                "m1_hybrid_priority": "요청 v2 0.72/0.28·67.5/82.5",
                "m1_evidence_priority": "이전 v3 pre-event 0.99 OR leadtime 0.97",
                "m1_risk_pre_event_priority": "현재 공식 v4 Risk 0.78 OR pre-event 0.99",
            }
        )
        priority_table["판정"] = priority_table["policy"].replace(
            {
                "current_best_priority": "기준 비교",
                "m1_specialist_priority": "보조 모델",
                "legacy_priority": "rollback 기준",
                "m1_hybrid_priority": "보수적 비교값",
                "m1_evidence_priority": "이전 v3 비교값",
                "m1_risk_pre_event_priority": "공식·신규 이벤트 감시",
            }
        )
        priority_table = priority_table[
            [
                "설정", "row_count", "precision", "recall", "f1", "false_positive_rate",
                "fault_events", "detected_fault_events", "fault_event_recall", "판정",
            ]
        ].rename(
            columns={
                "row_count": "표본 수", "precision": "정밀도", "recall": "재현율",
                "f1": "F1", "false_positive_rate": "오경보율",
                "fault_events": "고장 이벤트", "detected_fault_events": "탐지 이벤트",
                "fault_event_recall": "이벤트 재현율",
            }
        )

        hybrid_selected = read_csv(paths["hybrid_selected"])

        cls_eval = read_csv(paths["priority_lgbm_rule"])
        priority_body_table = cls_eval[
            cls_eval["split"].eq("holdout")
            & cls_eval["model_key"].isin(["rule_based", "lgbm_priority_only"])
        ][
            [
                "model", "n", "level_accuracy", "level_macro_f1", "action_precision",
                "action_recall", "action_specificity", "action_f1",
            ]
        ].copy()
        priority_body_table["오경보율"] = 1.0 - priority_body_table["action_specificity"]
        priority_body_table["판정"] = priority_body_table["model"].map(
            {
                "Rule-based v2_threshold48": "Rule body 유지 근거",
                "LGBM priority-only package": "일반화 성능 미달",
            }
        )
        priority_body_table = priority_body_table.rename(
            columns={
                "model": "모델", "n": "표본 수", "level_accuracy": "등급 정확도",
                "level_macro_f1": "등급 Macro-F1", "action_precision": "액션 정밀도",
                "action_recall": "액션 재현율", "action_specificity": "액션 특이도",
                "action_f1": "액션 F1",
            }
        )

        performance_tables = {
            "01_anomaly_performance_ko.csv": anomaly_table,
            "02_risk_performance_ko.csv": risk_table,
            "03_leadtime_performance_ko.csv": leadtime_table,
            "04_priority_active_performance_ko.csv": priority_table,
            "04b_priority_body_benchmark_ko.csv": priority_body_table,
        }
        for filename, frame in performance_tables.items():
            frame.to_csv(
                PPT_TABLE_DIR / filename,
                index=False,
                encoding="utf-8-sig",
                float_format="%.4f",
                lineterminator="\n",
            )

        display(Markdown("### 이상탐지 성능"))
        display(anomaly_table.round(4))
        display(Markdown("### Risk 성능"))
        display(risk_table.round(4))
        display(Markdown("### Leadtime 성능"))
        display(leadtime_table.round(4))
        display(Markdown("### 현재 Priority·Hybrid 성능"))
        display(priority_table.round(4))
        display(Markdown("### Priority 본체 비교 계약"))
        display(priority_body_table.round(4))
        """
    ),
    md(
        """
        # 페이지 1 — ML 성능 검증

        ## 검증된 Risk·Leadtime artifact를 복원해 내부 임시 재학습보다 일반화를 개선했다

        상위 `current-best` 보존본에서는 이전 promoted 후보보다 Risk와 Leadtime이 개선됐다.
        이 표는 **동일한 상위 holdout 계약 안의 후보 비교**다.
        """
    ),
    code(
        r"""
        best = read_csv(paths["upstream_best_comparison"])
        risk_models = {
            "previous_promoted_risk": "이전 promoted Risk",
            "best_risk_event_temporal": "상위 current-best Risk",
        }
        risk_compare = (
            best[best["model"].isin(risk_models) & best["metric"].isin(["precision", "recall", "f1", "false_positive_rate", "roc_auc"])]
            .pivot(index="model", columns="metric", values="value")
            .rename(index=risk_models)
            .reset_index(names="모델")
        )
        display(risk_compare.round(4))

        risk_long = risk_compare.melt(
            id_vars="모델",
            value_vars=["precision", "recall", "f1", "false_positive_rate"],
            var_name="지표",
            value_name="값",
        )
        risk_long["지표"] = risk_long["지표"].replace(
            {"precision": "정밀도", "recall": "재현율", "f1": "F1", "false_positive_rate": "오경보율"}
        )
        fig = px.bar(
            risk_long,
            x="지표",
            y="값",
            color="모델",
            barmode="group",
            text=risk_long["값"].round(3),
            color_discrete_sequence=[COLORS["gray"], COLORS["blue"]],
            title="상위 Risk 후보 비교 (동일 holdout)",
        )
        fig.update_layout(template="plotly_white", yaxis_range=[0, 1], legend_title="")
        fig.show()

        lead_models = {
            "previous_promoted_leadtime": "이전 promoted Leadtime",
            "best_leadtime": "상위 current-best Leadtime",
        }
        lead_compare = (
            best[best["model"].isin(lead_models) & best["metric"].isin(["accuracy", "macro_f1", "weighted_f1", "top2_accuracy", "bucket_distance_mae"])]
            .pivot(index="model", columns="metric", values="value")
            .rename(index=lead_models)
            .reset_index(names="모델")
        )
        display(lead_compare.round(4))
        """
    ),
    code(
        r"""
        local_risk = read_csv(paths["local_risk"])
        local_lead = read_csv(paths["local_leadtime"])
        risk_holdout = local_risk[local_risk["split"].eq("holdout")].iloc[0]
        lead_holdout = local_lead[local_lead["split"].eq("holdout")].iloc[0]

        local_revalidation = pd.DataFrame(
            [
                ["복원 Risk", int(risk_holdout["row_count"]), risk_holdout["precision"], risk_holdout["recall"], risk_holdout["f1"], risk_holdout["false_positive_rate"], risk_holdout["roc_auc"]],
                ["복원 Leadtime", int(lead_holdout["row_count"]), np.nan, np.nan, lead_holdout["macro_f1"], np.nan, np.nan],
            ],
            columns=["활성 모델 재검증", "holdout 행", "정밀도", "재현율", "F1/macro-F1", "오경보율", "ROC-AUC"],
        )
        display(local_revalidation.round(4))

        display(Markdown(
            f'''
        **재검증 판정**

        - 상위 Risk: F1 `{risk_compare.loc[risk_compare['모델'].eq('상위 current-best Risk'), 'f1'].iloc[0]:.3f}`, 오경보율 `{risk_compare.loc[risk_compare['모델'].eq('상위 current-best Risk'), 'false_positive_rate'].iloc[0]:.3f}`.
        - 복원 Risk: 정밀도 `{risk_holdout['precision']:.3f}`, F1 `{risk_holdout['f1']:.3f}`, 오경보율 `{risk_holdout['false_positive_rate']:.3f}`, ROC-AUC `{risk_holdout['roc_auc']:.3f}`.
        - 복원 Leadtime: macro-F1 `{lead_holdout['macro_f1']:.3f}`, Top-2 accuracy `{lead_holdout['top2_accuracy']:.3f}`.

        현재 수치는 복원 artifact를 동일 M1 event-regime split에서 다시 채점한 결과다.
        상위 보존본의 다른 계약 수치는 후보 선택 근거로만 분리 표기한다.
        '''
        ))
        """
    ),
    code(
        r"""
        grid_broad = read_csv(paths["grid_broad"])
        broad_rows = grid_broad[
            (grid_broad["metric_scope"].eq("row"))
            & grid_broad["policy"].isin(["grid_beststyle_risk_high", "best_risk_high_or_critical"])
        ].copy()
        broad_rows["f1"] = [f1_score(p, r) for p, r in zip(broad_rows["precision"], broad_rows["recall"])]
        broad_rows["후보"] = broad_rows["policy"].replace(
            {"grid_beststyle_risk_high": "Grid best-style Risk", "best_risk_high_or_critical": "Current-best Risk"}
        )
        display(broad_rows[["후보", "row_count", "precision", "recall", "f1", "false_positive_rate"]].round(4))

        display(Markdown(
            '''
        **페이지 1용 한 줄 결론:** 상위 current-best 계열은 이전 Risk/Leadtime과 Grid 도전자보다 안정적이었지만,
        복원 artifact는 낮은 Risk FPR과 높은 Leadtime Top-2를 재현했다. 다만 Risk recall은 36.4%이므로 Priority v4에서 pre-event 근거를 결합한다.
        '''
        ))
        """
    ),
    md(
        """
        # 페이지 2 — 운영 우선순위 검증

        ## Rule-based priority는 LGBM보다 안정적이지만, 현재 hybrid 임계값은 재보정이 필요하다

        기존 PPT의 `10/10`, `25.6h`, `9.3%`는 상위 운영 holdout에서
        `priority_high_or_urgent` 정책을 평가한 값이다.
        아래 액션 지표 `정밀도 88.4% / 재현율 71.0% / F1 78.8% / 특이도 96.1%`는
        별도의 366행 priority action 계약에서 나온 값이므로 표본과 정의를 따로 표시해야 한다.
        """
    ),
    code(
        r"""
        ops = read_csv(paths["upstream_ops"])
        ops_holdout = ops[(ops["scope"].eq("holdout")) & (ops["policy"].eq("priority_high_or_urgent"))].iloc[0]

        top_cards = pd.DataFrame(
            [
                ["고장 이벤트 사전 탐지", f"{int(ops_holdout['detected_fault_events'])}/{int(ops_holdout['total_fault_events'])}", "상위 운영 holdout"],
                ["최초 경보 중앙 리드타임", f"{ops_holdout['median_first_alarm_lead_hours']:.1f}h", "상위 운영 holdout"],
                ["정상 구간 오경보율", f"{100 * ops_holdout['normal_false_row_rate']:.1f}%", "상위 운영 holdout"],
            ],
            columns=["운영 지표", "값", "검증 계약"],
        )
        display(top_cards)

        cls = read_csv(paths["priority_lgbm_rule"])
        holdout_cls = cls[(cls["split"].eq("holdout")) & cls["model_key"].isin(["rule_based", "lgbm_priority_only"])].copy()
        holdout_cls["모델"] = holdout_cls["model_key"].replace(
            {"rule_based": "Rule-based v2_threshold48", "lgbm_priority_only": "LGBM priority"}
        )
        action_table = holdout_cls[["모델", "n", "action_precision", "action_recall", "action_f1", "action_specificity"]].copy()
        display(action_table.round(4))

        action_long = action_table.melt(
            id_vars=["모델", "n"],
            value_vars=["action_precision", "action_recall", "action_f1", "action_specificity"],
            var_name="지표",
            value_name="값",
        )
        action_long["지표"] = action_long["지표"].replace(
            {"action_precision": "정밀도", "action_recall": "재현율", "action_f1": "F1", "action_specificity": "특이도"}
        )
        fig = px.bar(
            action_long,
            x="지표",
            y="값",
            color="모델",
            barmode="group",
            text=action_long["값"].round(3),
            color_discrete_sequence=[COLORS["navy"], COLORS["orange"]],
            title="운영 액션 분류: Rule-based vs LGBM (holdout 366행)",
        )
        fig.update_layout(template="plotly_white", yaxis_range=[0, 1], legend_title="")
        fig.show()
        """
    ),
    code(
        r"""
        active = read_csv(paths["active_priority"])
        official_row = active[
            active["policy"].eq("m1_risk_pre_event_priority")
            & active["split"].eq("holdout")
            & active["metric_scope"].eq("row")
        ].iloc[0]
        official_event = active[
            active["policy"].eq("m1_risk_pre_event_priority")
            & active["split"].eq("holdout")
            & active["metric_scope"].eq("fault_event")
        ].iloc[0]
        requested_v2_row = active[
            active["policy"].eq("m1_hybrid_priority")
            & active["split"].eq("holdout")
            & active["metric_scope"].eq("row")
        ].iloc[0]
        requested_v2_event = active[
            active["policy"].eq("m1_hybrid_priority")
            & active["split"].eq("holdout")
            & active["metric_scope"].eq("fault_event")
        ].iloc[0]
        legacy_row = active[
            active["policy"].eq("legacy_priority")
            & active["split"].eq("holdout")
            & active["metric_scope"].eq("row")
        ].iloc[0]
        legacy_event = active[
            active["policy"].eq("legacy_priority")
            & active["split"].eq("holdout")
            & active["metric_scope"].eq("fault_event")
        ].iloc[0]
        hybrid_summary = read_csv(paths["hybrid_selection"])
        recal_065 = hybrid_summary[
            hybrid_summary["selection_name"].eq("legacy_recalibrated_0p65") & hybrid_summary["split"].eq("holdout")
        ].iloc[0]
        best_072 = hybrid_summary[
            hybrid_summary["selection_name"].eq("holdout_best_guardrail") & hybrid_summary["split"].eq("holdout")
        ].iloc[0]

        hybrid_compare = pd.DataFrame(
            [
                ["rollback v1", 0.65, 0.35, 82.5, 95.0, legacy_row["precision"], legacy_row["recall"], f1_score(legacy_row["precision"], legacy_row["recall"]), legacy_row["false_positive_rate"], legacy_event["fault_event_recall"]],
                ["요청 v2", 0.72, 0.28, m1_meta["m1_hybrid_thresholds"]["high"], m1_meta["m1_hybrid_thresholds"]["urgent"], requested_v2_row["precision"], requested_v2_row["recall"], f1_score(requested_v2_row["precision"], requested_v2_row["recall"]), requested_v2_row["false_positive_rate"], requested_v2_event["fault_event_recall"]],
                ["공식 Risk/pre-event v4", np.nan, np.nan, 99.0, 99.8, official_row["precision"], official_row["recall"], f1_score(official_row["precision"], official_row["recall"]), official_row["false_positive_rate"], official_event["fault_event_recall"]],
            ],
            columns=["설정", "current-best 가중치", "M1 가중치", "high", "urgent", "정밀도", "재현율", "F1", "오경보율", "이벤트 재현율"],
        )
        display(hybrid_compare.round(4))

        evidence_sweep = read_csv(paths["evidence_gate_sweep"])
        evidence_selected = evidence_sweep[evidence_sweep["selected_official_v4"].astype(str).str.lower().eq("true")]
        display(Markdown("**공식 v4 선택 임계값의 train/validation/holdout 재현값**"))
        display(evidence_selected[[
            "split", "risk_threshold", "pre_event_threshold", "precision", "recall", "f1",
            "false_positive_rate", "fault_event_recall", "tp", "fp", "fn", "tn",
        ]].round(4))

        hybrid_long = hybrid_compare.melt(
            id_vars=["설정"],
            value_vars=["정밀도", "재현율", "F1", "오경보율", "이벤트 재현율"],
            var_name="지표",
            value_name="값",
        )
        fig = px.bar(
            hybrid_long,
            x="지표",
            y="값",
            color="설정",
            barmode="group",
            text=hybrid_long["값"].round(3),
            color_discrete_sequence=[COLORS["red"], COLORS["sky"], COLORS["green"]],
            title="M1 Priority: rollback v1 vs 요청 v2 vs 공식 Risk/pre-event v4",
        )
        fig.update_layout(template="plotly_white", yaxis_range=[0, 1], legend_title="")
        fig.show()
        """
    ),
    md(
        """
        **페이지 2용 판정**

        - Priority 모델 본체는 **Rule-based v2_threshold48 유지**가 타당하다. LGBM은 holdout 액션 F1과 Top-K 일반화가 낮다.
        - legacy v1 `0.65/0.35 + 82.5/95.0`은 rollback 기준으로 보존한다.
        - 요청 v2 `0.72/0.28 + 67.5/82.5`는 복원 artifact에서 정밀도 100.0%, 재현율 53.2%, F1 69.5%, FPR 0.0%, 이벤트 7/8인 보수적 비교값이다.
        - 공식 v4 `Risk >= 0.78 OR pre-event >= 0.99`는 정밀도 83.6%, 재현율 72.7%, F1 77.8%, FPR 10.4%, 이벤트 7/8이다.
        - v4는 validation과 holdout에서 v2보다 높은 F1·재현율을 확보했지만 장기 FPR 목표 5%는 아직 미달이므로 신규 이벤트에서 계속 감시한다.
        """
    ),
    md(
        """
        # 페이지 3 — Agent 구성

        ## 단일 Agent가 아니라, 검증·근거·진단·승인·보고를 분리한 9단계 LangGraph v2

        현재 코드는 `agent_graph_v2.v3` 계약으로 9개 단계를 순서대로 실행하고,
        단계별 snapshot/hash/checkpoint를 저장한다. 오류가 난 단계부터 targeted rerun이 가능하며,
        근거 부족·모델 불일치·고우선순위는 상위 재판정 또는 사람 검토로 보낸다.
        """
    ),
    code(
        r"""
        stage_source = paths["stages"].read_text(encoding="utf-8")
        match = re.search(r"STAGE_ORDER:.*?= \((.*?)\)", stage_source, flags=re.S)
        if match is None:
            raise RuntimeError("STAGE_ORDER를 파싱하지 못했습니다.")
        stages = re.findall(r'"([a-z_]+)"', match.group(1))
        stage_labels = {
            "ml_validation": "ML 예측 재검증",
            "weather_context": "기상·현장 맥락",
            "rag_retrieval": "RAG 근거 검색",
            "rag_interpretation": "근거 해석",
            "fault_analysis": "고장 원인 분석",
            "higher_model_reassessment": "상위 모델 재판정",
            "parent_disposition": "승인·사람 검토 분기",
            "report_draft": "조치안·보고서 초안",
            "report_fidelity": "보고서 근거 충실도",
        }
        stage_groups = {
            "ml_validation": "검증",
            "weather_context": "근거 수집",
            "rag_retrieval": "근거 수집",
            "rag_interpretation": "근거 수집",
            "fault_analysis": "진단·판정",
            "higher_model_reassessment": "진단·판정",
            "parent_disposition": "진단·판정",
            "report_draft": "출력 보증",
            "report_fidelity": "출력 보증",
        }
        stage_table = pd.DataFrame(
            [{"순서": i + 1, "코드 단계": name, "화면용 명칭": stage_labels[name], "역할군": stage_groups[name]} for i, name in enumerate(stages)]
        )
        display(stage_table)

        node_names = ["Priority Card"] + [stage_labels[name] for name in stages] + ["운영자 UI"]
        group_colors = {
            "입력": COLORS["gray"],
            "검증": COLORS["blue"],
            "근거 수집": COLORS["sky"],
            "진단·판정": COLORS["purple"],
            "출력 보증": COLORS["green"],
            "출력": COLORS["orange"],
        }
        node_colors = [group_colors["입력"]] + [group_colors[stage_groups[name]] for name in stages] + [group_colors["출력"]]
        fig = go.Figure(
            go.Sankey(
                arrangement="snap",
                node=dict(label=node_names, color=node_colors, pad=16, thickness=18),
                link=dict(
                    source=list(range(len(node_names) - 1)),
                    target=list(range(1, len(node_names))),
                    value=[1] * (len(node_names) - 1),
                    color="rgba(45,108,223,0.18)",
                ),
            )
        )
        fig.update_layout(title="Agent Graph v2 실제 9단계", height=560, font_size=12)
        fig.show()
        """
    ),
    code(
        r"""
        settings_text = paths["settings"].read_text(encoding="utf-8")
        keys = [
            "integrated_agent_model",
            "independent_agent_model",
            "rejudge_model",
            "work_order_model",
            "report_model",
            "rag_quality_enabled",
            "answer_quality_enabled",
        ]
        settings_values = {}
        for key in keys:
            value_match = re.search(rf"^\s*{key}:\s*\w+\s*=\s*(.+)$", settings_text, flags=re.M)
            settings_values[key] = value_match.group(1).strip().strip('"') if value_match else "확인 실패"

        model_roles = pd.DataFrame(
            [
                ["통합 판단·조치안", settings_values["integrated_agent_model"], "기본 reasoning"],
                ["독립 고장 진단", settings_values["independent_agent_model"], "고우선순위/불일치 시 별도 진단"],
                ["상위 재판정·품질 judge", settings_values["rejudge_model"], "불확실성/품질 재검토"],
                ["작업지시 초안", settings_values["work_order_model"], "정형 출력"],
                ["운영 보고서", settings_values["report_model"], "정형 보고"],
            ],
            columns=["역할", "현재 기본 모델", "분리 이유"],
        )
        display(model_roles)

        feature_flags = pd.DataFrame(
            [
                ["RAG 품질 재평가", settings_values["rag_quality_enabled"], "기본값은 비활성"],
                ["답변 품질 judge", settings_values["answer_quality_enabled"], "기본값은 비활성"],
            ],
            columns=["품질 기능", "현재 기본값", "발표 시 주의"],
        )
        display(feature_flags)
        """
    ),
    md(
        """
        **페이지 3용 한 줄 결론:** `Priority Card → ML 재검증 → 기상/RAG 근거 → 고장 분석 → 상위 재판정·사람 검토 → 보고서 충실도`의
        9단계 구조다. 화면에는 결과만 전달하지만, 내부적으로는 단계별 snapshot과 근거 lineage를 남긴다.

        발표 시 주의:

        - RAG 품질 평가와 답변 품질 judge는 코드에 있으나 기본 설정이 `False`다. 활성 기능처럼 표현하지 않는다.
        - Agent가 ML 점수를 임의로 다시 만드는 구조가 아니라, 저장된 Priority Card를 검증·해석하는 구조다.
        - 자동 정비 확정이 아니라 사람 승인/재검토를 포함하는 운영 보조 구조다.
        """
    ),
    md(
        """
        # Agent 1사이클·재생성 비용, 호출량, 시간 평가

        비용은 2026-07-22 OpenAI 공식 표준 API 단가를 사용한다.

        - GPT-5.4 mini: 입력 `$0.75`, 캐시 입력 `$0.075`, 출력 `$4.50` / 1M tokens
        - GPT-5.4 nano: 입력 `$0.20`, 캐시 입력 `$0.02`, 출력 `$1.25` / 1M tokens
        - GPT-5.4: 입력 `$2.50`, 캐시 입력 `$0.25`, 출력 `$15.00` / 1M tokens

        공식 근거:

        - https://developers.openai.com/api/docs/models/gpt-5.4-mini
        - https://developers.openai.com/api/docs/models/gpt-5.4-nano
        - https://developers.openai.com/api/docs/models/gpt-5.4

        실제 관측 표본은 로컬 PostgreSQL의 `agent_runs`, `agent_run_events`에서 2026-07-21 완료된
        OpenAI 실행 7건을 읽어 고정한 것이다. 현재 기본 실행은 `agent_graph:v1`이며,
        운영자 교정에 의한 특정 단계 재실행 `agent_graph:v2`는 실운영 표본이 아직 없다.
        """
    ),
    code(
        r"""
        pricing = pd.DataFrame(
            [
                ["gpt-5.4-mini", 0.75, 0.075, 4.50, "기본 AI 조치·검토 챗"],
                ["gpt-5.4-nano", 0.20, 0.020, 1.25, "작업지시서·이상 보고서"],
                ["gpt-5.4", 2.50, 0.250, 15.00, "상위 재판정·품질 Judge"],
            ],
            columns=["모델", "입력 $/1M", "캐시입력 $/1M", "출력 $/1M", "현재 역할"],
        )
        display(pricing)

        price_lookup = {
            row["모델"]: {
                "input": row["입력 $/1M"],
                "cached": row["캐시입력 $/1M"],
                "output": row["출력 $/1M"],
            }
            for _, row in pricing.iterrows()
        }

        def planned_cost(
            model: str,
            input_tokens: int,
            output_tokens: int,
            cached_input_tokens: int = 0,
        ) -> float:
            rate = price_lookup[model]
            regular = max(input_tokens - cached_input_tokens, 0)
            return (
                regular * rate["input"]
                + cached_input_tokens * rate["cached"]
                + output_tokens * rate["output"]
            ) / 1_000_000

        observations = read_csv(paths["agent_observations"])
        observations["전체 API 호출 수(보고서 포함)"] = (
            observations["model_calls"] + observations["report_call_attempted"]
        )
        observations["보고서 성공"] = observations["report_call_status"].eq("completed")

        actual_cycle_summary = pd.DataFrame(
            [
                ["표본 수", len(observations), len(observations), len(observations), "2026-07-21 실제 완료 LLM run"],
                ["기본 Agent LLM 호출", observations["model_calls"].min(), observations["model_calls"].mean(), observations["model_calls"].max(), "gpt-5.4-mini; DB token_usage 집계"],
                ["보고서 포함 API 호출", observations["전체 API 호출 수(보고서 포함)"].min(), observations["전체 API 호출 수(보고서 포함)"].mean(), observations["전체 API 호출 수(보고서 포함)"].max(), "nano 보고서 호출 1회 추가"],
                ["총 토큰", observations["total_tokens"].min(), observations["total_tokens"].mean(), observations["total_tokens"].max(), "보고서 nano 토큰 제외"],
                ["기본 Agent 비용(USD)", observations["logged_main_cost_usd"].min(), observations["logged_main_cost_usd"].mean(), observations["logged_main_cost_usd"].max(), "보고서 nano 비용 제외"],
                ["전체 소요시간(초)", observations["duration_seconds"].min(), observations["duration_seconds"].mean(), observations["duration_seconds"].max(), "큐 등록~완료"],
                ["보고서 단계 시간(초)", observations["report_call_seconds"].min(), observations["report_call_seconds"].mean(), observations["report_call_seconds"].max(), "전체 시간에 포함"],
                ["보고서 성공률", observations["보고서 성공"].mean(), observations["보고서 성공"].mean(), observations["보고서 성공"].mean(), "5/7 성공"],
            ],
            columns=["지표", "최소", "평균", "최대", "해석"],
        )
        display(actual_cycle_summary.round(6))

        retry_obs = observations[observations["output_retry_count"].eq(1)].copy()
        retry_summary = pd.DataFrame(
            [
                ["관측 건수", len(retry_obs), len(retry_obs), len(retry_obs), "출력 검증 실패 후 1회 재생성"],
                ["추가 시간(초)", retry_obs["retry_elapsed_seconds"].min(), retry_obs["retry_elapsed_seconds"].mean(), retry_obs["retry_elapsed_seconds"].max(), "output_retry 이벤트~재생성 완료"],
                ["재생성 귀속 토큰", retry_obs["retry_attributed_tokens"].min(), retry_obs["retry_attributed_tokens"].mean(), retry_obs["retry_attributed_tokens"].max(), "마지막 고용량 호출을 재생성으로 귀속한 추정"],
                ["재생성 귀속 비용(USD)", retry_obs["retry_attributed_cost_usd"].min(), retry_obs["retry_attributed_cost_usd"].mean(), retry_obs["retry_attributed_cost_usd"].max(), "호출 순서 기반 추정; 별도 stage usage 미저장"],
            ],
            columns=["재생성 지표", "최소", "평균", "최대", "해석"],
        )
        display(retry_summary.round(6))

        # 보고서 모듈은 Responses API usage를 저장하지 않는다. 아래는 명시한 토큰 가정의 계획값이다.
        nano_report_base_cost = planned_cost("gpt-5.4-nano", 8_000, 3_000)
        nano_draft_cost = planned_cost("gpt-5.4-nano", 7_000, 800)
        mini_chat_cost = planned_cost("gpt-5.4-mini", 5_000, 500)
        mini_revision_cost = planned_cost("gpt-5.4-mini", 2_000, 500)
        high_rejudge_cost = planned_cost("gpt-5.4", 7_000, 800)
        high_quality_cost = planned_cost("gpt-5.4", 7_000, 300)

        child_obs = observations[observations["lineage_kind"].eq("child")]
        cost_scenarios = pd.DataFrame(
            [
                [
                    "현재 V1 1사이클(실측 평균)",
                    "gpt-5.4-mini + gpt-5.4-nano",
                    f"mini {observations['model_calls'].mean():.2f}회 + nano 1회",
                    f"{observations['duration_seconds'].mean():.1f}초 (44.6~93.7초)",
                    observations["logged_main_cost_usd"].mean() + nano_report_base_cost,
                    "mini 비용 실측 + nano 8k 입력/3k 출력 계획값",
                    "현재 기본 agent_graph:v1",
                ],
                [
                    "출력 재생성 1회 추가",
                    "gpt-5.4-mini",
                    "+1회",
                    f"+{retry_obs['retry_elapsed_seconds'].mean():.1f}초 (3.6~6.4초)",
                    retry_obs["retry_attributed_cost_usd"].mean(),
                    "3건의 마지막 고용량 호출 귀속 평균",
                    "현재 V1 출력 검증 실패 경로",
                ],
                [
                    "전체 수동 재실행",
                    "gpt-5.4-mini + gpt-5.4-nano",
                    f"mini {child_obs['model_calls'].mean():.2f}회 + nano 1회",
                    f"{child_obs['duration_seconds'].mean():.1f}초",
                    child_obs["logged_main_cost_usd"].mean() + nano_report_base_cost,
                    "실제 child 4건 mini 평균 + nano 계획값",
                    "이전 실행 재사용 없이 새 V1 사이클",
                ],
                [
                    "V2 보고서 단계만 재실행",
                    "gpt-5.4-nano",
                    "1회",
                    "계약 30초/호출; 실측 표본 없음",
                    nano_draft_cost,
                    "7k 입력/800 출력 계획값",
                    "이전 7개 stage snapshot 재사용",
                ],
                [
                    "V2 ML 단계부터 재실행·상위 재판정",
                    "gpt-5.4 + gpt-5.4-nano",
                    "최대 2회",
                    "계획상 최대 약 60초; 실측 표본 없음",
                    high_rejudge_cost + nano_draft_cost,
                    "각 7k 입력/800 출력 계획값",
                    "ML 품질 insufficient/unavailable일 때 high-model 1회",
                ],
                [
                    "Answer quality 실패 후 자동 재생성",
                    "gpt-5.4-nano + gpt-5.4",
                    "nano 2회 + GPT-5.4 Judge 2회",
                    "호출 직렬 실행; 실측 표본 없음",
                    2 * nano_draft_cost + 2 * high_quality_cost,
                    "draft 7k/800, judge 7k/300 계획값",
                    "현재 answer_quality_enabled=False",
                ],
                [
                    "검토 챗 일반 질문",
                    "gpt-5.4-mini",
                    "1회",
                    "별도 latency 계측 없음",
                    mini_chat_cost,
                    "5k 입력/500 출력 계획값",
                    "대화 24개 turn + 운영 문맥 포함 가능",
                ],
                [
                    "작업지시서 범위 수정 초안",
                    "gpt-5.4-mini",
                    "1회",
                    "별도 latency 계측 없음",
                    mini_revision_cost,
                    "2k 입력/500 출력 계획값",
                    "의도 파싱은 규칙 기반; 본문 치환만 LLM",
                ],
                [
                    "수정안 확정",
                    "없음",
                    "0회",
                    "DB 처리만",
                    0.0,
                    "LLM 비용 없음",
                    "승인/수정 확정은 결정론적 처리",
                ],
            ],
            columns=["시나리오", "사용 모델", "LLM 호출량", "시간", "예상 비용 USD", "비용 근거", "현재 상태"],
        )
        display(cost_scenarios.round({"예상 비용 USD": 6}))

        call_matrix = pd.DataFrame(
            [
                ["V1 Evidence loop", "gpt-5.4-mini", "1~4회(설정)", "실측 1~5 decision event", "근거 충분성 판단"],
                ["V1 운영 답변", "gpt-5.4-mini", "1회 이상", "구조화 출력·도구 turn에 따라 증가", "token_usage 포함"],
                ["V1 출력 재생성", "gpt-5.4-mini", "0~1회", "실측 3/7건", "token_usage 포함"],
                ["이상 보고서 JSON", "gpt-5.4-nano", "1회", "실측 7/7 시도, 5/7 성공", "현재 token_usage 누락"],
                ["V2 상위 재판정", "gpt-5.4", "0~1회", "ML 품질 저하 시", "현재 V2 실측 없음"],
                ["V2 보고서 초안", "gpt-5.4-nano", "1회", "snapshot-only", "도구 호출 0"],
                ["V2 품질 Judge", "gpt-5.4", "0~2회", "초안·재생성안 각각 평가", "현재 비활성"],
                ["독립 고장 진단 Worker", "gpt-5.4-mini", "0~2회", "45초 + 15초, 총 60초 예산", "모델은 설정됐지만 현재 V2 fault stage 미연결"],
                ["내부 RAG 검색", "LLM 없음", "1회; broaden 시 최대 2회", "DB/vector 검색", "품질 기능 기본 비활성"],
                ["외부 Web 검색", "gpt-5.4-mini", "0~1회", "예산 $0.02/run", "현재 비활성"],
            ],
            columns=["단계", "모델", "호출량", "시간/조건", "계측 상태"],
        )
        display(call_matrix)

        agent_tables = {
            "05_openai_pricing_20260722.csv": pricing,
            "06_agent_actual_cycle_observations_ko.csv": observations,
            "07_agent_actual_cycle_summary_ko.csv": actual_cycle_summary,
            "08_agent_output_retry_summary_ko.csv": retry_summary,
            "09_agent_regeneration_cost_scenarios_ko.csv": cost_scenarios,
            "10_agent_model_call_matrix_ko.csv": call_matrix,
        }
        for filename, frame in agent_tables.items():
            frame.to_csv(
                PPT_TABLE_DIR / filename,
                index=False,
                encoding="utf-8-sig",
                float_format="%.8f",
                lineterminator="\n",
            )
        """
    ),
    md(
        """
        ## Agent 비용표 해석 시 반드시 적을 한계

        1. `agent_runs.token_usage`에는 기본 Agent의 GPT-5.4 mini 호출만 들어가며,
           `write_anomaly_report`의 GPT-5.4 nano 사용량은 현재 저장하지 않는다.
        2. 따라서 현재 화면/DB에 보이는 `$0.0068~$0.0116`은 완전한 1사이클 비용이 아니다.
           PPT에는 nano 보고서 계획비용을 더한 값을 사용하고 `추정`이라고 표시한다.
        3. V2 특정 단계 재실행, GPT-5.4 상위 재판정, answer-quality 자동 재생성은 실측 표본이 없다.
           호출 구조와 공식 단가로 계산한 계획값이며 실제값으로 표현하면 안 된다.
        4. 현재 V2 `fault_analysis`는 독립 진단 모델을 호출하지 않고 `unavailable` snapshot을 만든다.
           “고장진단 Agent가 매번 실행된다”는 표현은 현재 코드와 맞지 않는다.
        5. RAG quality, answer quality, external search는 기본 설정이 모두 비활성이다.
        """
    ),
    md(
        """
        ## PPT 제작 GPT에 전달할 3페이지 문안

        ### 1페이지 제목

        **검증된 Risk·Leadtime artifact 복원으로 일반화 성능을 회복했다**

        - 상위 Risk: 이전 F1 51.3% → current-best 69.0%, 오경보율 15.4% → 3.3%
        - 상위 Leadtime: 정확도 65.1% → 73.3%, bucket MAE 0.384 → 0.291
        - 복원 Risk: 정밀도 85.7%, 재현율 36.4%, F1 51.1%, 오경보율 4.7%, ROC-AUC 67.2%
        - 복원 Leadtime: macro-F1 69.3%, weighted-F1 70.8%, Top-2 98.5%
        - 결론: 낮은 Risk 오경보율을 유지하고 pre-event와 결합해 Priority recall을 보완한다.

        ### 2페이지 제목

        **복원 Risk와 pre-event를 결합한 Priority v4가 가장 높은 균형 성능을 냈다**

        - 상위 운영 정책: 10/10 고장 이벤트 탐지, 중앙 리드타임 25.6h, 정상 오경보율 9.3%
        - 동일 366행 액션 계약: Rule-based F1 78.8% vs LGBM 47.0%
        - rollback v1: 0.65/0.35 + 82.5/95.0, 정밀도 100.0%, F1 42.9%, FPR 0.0%, 이벤트 5/8
        - 요청 v2: 0.72/0.28 + 67.5/82.5, 정밀도 100.0%, F1 69.5%, FPR 0.0%, 이벤트 7/8
        - 공식 v4: Risk 0.78 OR pre-event 0.99, 정밀도 83.6%, 재현율 72.7%, F1 77.8%, FPR 10.4%, 이벤트 7/8
        - 결론: v4가 validation과 holdout에서 가장 높은 균형 F1을 냈다. 다만 FPR 5% 장기 목표와 신규 이벤트 검증은 남아 있다.

        ### 3페이지 제목

        **Agent는 단계별 재실행으로 비용을 통제하되, 현재 기본 실행은 V1이다**

        - 입력: 1,252행 × 67열 공식 Priority Card
        - 현재 V1 실측 7건: mini 3~7회 + nano 보고서 1회, 총 44.6~93.7초
        - DB 집계 mini 비용: 건당 평균 $0.0094; nano 보고서 계획값을 더한 1사이클 기준값은 약 $0.0148
        - 출력 재생성 1회: mini 1회 추가, 실측 +3.6~6.4초, 귀속비용 평균 약 $0.0051
        - V2 보고서 단계만 재실행: 이전 snapshot을 재사용하고 nano 1회만 호출하는 구조
        - 주의: V2 targeted rerun·상위 재판정·품질 자동재생성은 아직 실측 표본이 없어 계획값으로만 표시
        """
    ),
    md(
        """
        ## 부록 A. DA·합성 스트레스 테스트를 최종 성능표에 섞지 않는 이유

        `da`의 rolling/rebaseline 후보는 장기 리드타임과 오경보 절충에 관한 중요한 운영 아이디어를 제공한다.
        그러나 window, 정상 구간, label 기반 제외 규칙이 현재 Agent Card 계약과 달라 독립적인 보조 근거로 사용한다.
        XAI4HEAT 합성 데이터는 민감도는 높지만 base false alarm이 매우 커서 도메인 이동 스트레스 테스트로만 해석한다.
        """
    ),
    code(
        r"""
        da = read_csv(paths["da_rebaseline"])
        display(da.round(4))

        xai = read_csv(paths["xai_mock"])
        xai_view = xai[["scenario", "prediction_column", "precision", "recall", "f1", "false_positive_rate"]].copy()
        display(xai_view.round(4))
        """
    ),
    md(
        """
        # 부록 B. 모델별 확장 수치 검증

        아래 표는 기존 Precision·Recall·F1 표에 정확도, 균형정확도, 특이도, 음성예측도,
        MCC, Cohen's Kappa, 확률 보정오차, 순서형 오차, Top-K/NDCG, 분포 이동과 신뢰구간을 더한 것이다.

        - **분류 성능**은 모델이 정답을 얼마나 잘 맞히는지 본다.
        - **확률 보정**은 80%라고 말한 예측이 실제로도 약 80% 맞는지 본다.
        - **운영 성능**은 고장 이벤트를 놓치지 않으면서 오경보와 알람량을 통제하는지 본다.
        - **강건성**은 시간·계절·설비 조건이 바뀌어도 성능이 유지되는지 본다.
        - **불확실성**은 작은 표본에서 나온 한 개의 점수가 얼마나 흔들릴 수 있는지 본다.

        수치는 현재 로컬 산출물로 계산 가능한 범위만 채웠다. 제조사 외부검증, V2 Agent 실측,
        사람 평가처럼 데이터가 없는 항목은 뒤의 `추가 검증 백로그`에 별도로 표시한다.
        """
    ),
    code(
        r"""
        from math import sqrt

        from scipy.stats import ks_2samp
        from sklearn.metrics import (
            accuracy_score,
            average_precision_score,
            balanced_accuracy_score,
            brier_score_loss,
            cohen_kappa_score,
            confusion_matrix,
            f1_score as sk_f1_score,
            log_loss,
            matthews_corrcoef,
            precision_recall_fscore_support,
            precision_score,
            recall_score,
            roc_auc_score,
            top_k_accuracy_score,
        )

        def safe_div(numerator: float, denominator: float) -> float:
            return float(numerator / denominator) if denominator else float("nan")

        def binary_metrics(y_true, y_pred, y_score=None) -> dict:
            y_true = np.asarray(y_true, dtype=int)
            y_pred = np.asarray(y_pred, dtype=int)
            tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
            result = {
                "표본수": len(y_true),
                "양성수": int(y_true.sum()),
                "TP": int(tp), "FP": int(fp), "FN": int(fn), "TN": int(tn),
                "정확도": accuracy_score(y_true, y_pred),
                "균형정확도": balanced_accuracy_score(y_true, y_pred),
                "정밀도": precision_score(y_true, y_pred, zero_division=0),
                "재현율": recall_score(y_true, y_pred, zero_division=0),
                "특이도": safe_div(tn, tn + fp),
                "음성예측도_NPV": safe_div(tn, tn + fn),
                "F1": sk_f1_score(y_true, y_pred, zero_division=0),
                "MCC": matthews_corrcoef(y_true, y_pred),
                "Cohen_Kappa": cohen_kappa_score(y_true, y_pred),
                "오경보율_FPR": safe_div(fp, fp + tn),
                "알람률": float(y_pred.mean()),
                "양성비율": float(y_true.mean()),
            }
            if y_score is not None and len(np.unique(y_true)) == 2:
                score = np.asarray(y_score, dtype=float)
                result["ROC_AUC"] = roc_auc_score(y_true, score)
                result["Average_Precision"] = average_precision_score(y_true, score)
            return result

        def binary_ece(y_true, probability, bins: int = 10) -> float:
            y_true = np.asarray(y_true, dtype=int)
            probability = np.clip(np.asarray(probability, dtype=float), 0.0, 1.0)
            edges = np.linspace(0.0, 1.0, bins + 1)
            bucket = np.minimum(np.digitize(probability, edges[1:-1], right=True), bins - 1)
            ece = 0.0
            for index in range(bins):
                mask = bucket == index
                if mask.any():
                    ece += mask.mean() * abs(y_true[mask].mean() - probability[mask].mean())
            return float(ece)

        def confidence_ece(y_true, y_pred, confidence, bins: int = 10) -> float:
            correct = (np.asarray(y_true) == np.asarray(y_pred)).astype(int)
            return binary_ece(correct, confidence, bins=bins)

        def wilson_interval(successes: int, total: int, z: float = 1.95996398454) -> tuple[float, float]:
            if total <= 0:
                return float("nan"), float("nan")
            p = successes / total
            denominator = 1 + z * z / total
            center = (p + z * z / (2 * total)) / denominator
            half = z * sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
            return center - half, center + half

        def population_stability_index(reference, comparison, bins: int = 10) -> float:
            reference = pd.Series(reference).dropna().astype(float).to_numpy()
            comparison = pd.Series(comparison).dropna().astype(float).to_numpy()
            quantiles = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
            if len(quantiles) < 3:
                return float("nan")
            quantiles[0], quantiles[-1] = -np.inf, np.inf
            ref_count, _ = np.histogram(reference, bins=quantiles)
            cmp_count, _ = np.histogram(comparison, bins=quantiles)
            ref_rate = np.clip(ref_count / max(ref_count.sum(), 1), 1e-6, None)
            cmp_rate = np.clip(cmp_count / max(cmp_count.sum(), 1), 1e-6, None)
            return float(np.sum((cmp_rate - ref_rate) * np.log(cmp_rate / ref_rate)))

        metric_definitions = pd.DataFrame(
            [
                ["정확도", "(TP+TN)/전체", "전체 정답 비율", "높을수록 좋음", "불균형 데이터에서는 단독 사용 금지"],
                ["균형정확도", "(재현율+특이도)/2", "양성·음성을 같은 비중으로 평가", "높을수록 좋음", "Risk/이상탐지 핵심 보조지표"],
                ["정밀도", "TP/(TP+FP)", "발령한 알람 중 실제 고장 비율", "높을수록 좋음", "현장 불필요 출동과 연결"],
                ["재현율", "TP/(TP+FN)", "실제 고장 사전구간을 잡은 비율", "높을수록 좋음", "미탐 비용과 연결"],
                ["특이도", "TN/(TN+FP)", "정상 구간을 정상으로 유지한 비율", "높을수록 좋음", "1-FPR"],
                ["음성예측도(NPV)", "TN/(TN+FN)", "정상 판정이 실제 정상일 확률", "높을수록 좋음", "알람이 없을 때 신뢰성"],
                ["F1", "정밀도와 재현율의 조화평균", "오경보와 미탐의 균형", "높을수록 좋음", "운영비용 차이는 별도 반영"],
                ["MCC", "혼동행렬 4칸의 상관계수", "불균형에 강한 단일 요약값", "1에 가까울수록 좋음", "0은 무작위 수준"],
                ["Cohen's Kappa", "관측 일치-우연 일치 보정", "우연을 제외한 분류 일치", "1에 가까울수록 좋음", "클래스 비율 영향 확인"],
                ["ROC-AUC", "모든 임계값의 TPR-FPR 곡선 면적", "순위 분리 능력", "높을수록 좋음", "불균형에서는 AP와 함께 표시"],
                ["Average Precision", "PR 곡선 요약", "희소 양성의 순위 품질", "높을수록 좋음", "양성 비율을 기준선으로 함께 표시"],
                ["Brier score", "평균 (예측확률-정답)^2", "확률의 정확성과 보정", "낮을수록 좋음", "확률 의미가 있는 출력에만 적용"],
                ["Log-loss", "정답 클래스의 음의 로그확률", "확신한 오답을 크게 벌점", "낮을수록 좋음", "0/1 확률은 clipping 후 계산"],
                ["ECE-10", "10개 확률구간의 신뢰도-정확도 차이", "확률 보정 오차", "0에 가까울수록 좋음", "표본이 작으면 bin별 변동 큼"],
                ["Macro-F1", "클래스별 F1 단순평균", "희소 Leadtime 구간까지 동일 가중", "높을수록 좋음", "3-7d 성능을 숨기지 않음"],
                ["Weighted-F1", "클래스 표본수 가중 F1", "전체 체감 성능", "높을수록 좋음", "다수 클래스 영향 큼"],
                ["Top-2 정확도", "상위 2개 확률에 정답 포함 비율", "인접 후보 구간 제공 능력", "높을수록 좋음", "정확한 1순위와 함께 표시"],
                ["Bucket MAE", "평균 |예측구간 index-정답 index|", "Leadtime 구간 거리 오차", "낮을수록 좋음", "0-24h,1-3d,3-7d를 0,1,2로 인코딩"],
                ["지연 예측률", "예측 index가 정답보다 큰 비율", "실제보다 여유 있다고 판단한 위험 오차", "낮을수록 좋음", "조기 예측보다 운영 위험이 큼"],
                ["Event recall", "탐지된 고장이벤트/전체 고장이벤트", "같은 고장 창의 중복행을 한 건으로 평가", "높을수록 좋음", "행 재현율과 반드시 분리"],
                ["Precision@K", "상위 K건 중 양성 비율", "제한된 출동/검토 용량의 효율", "높을수록 좋음", "K=일일 처리 가능량으로 설정"],
                ["Recall@K", "상위 K건이 포착한 양성 비율", "처리용량 안에서의 커버리지", "높을수록 좋음", "Precision@K와 함께 표시"],
                ["NDCG@K", "상위 순위의 graded relevance 할인 누적이득", "긴급 고장을 앞에 배치하는 품질", "1에 가까울수록 좋음", "우선순위 모델 핵심"],
                ["PSI", "기준·비교 분포 비율 차이", "점수 분포 이동", "낮을수록 좋음", "일반 참고: <0.10 안정, 0.10~0.25 주의, >=0.25 큼"],
                ["KS 검정", "두 누적분포 최대 차이", "분포가 동일한지 통계검정", "p<0.05면 이동 의심", "표본수가 크면 작은 차이도 유의"],
                ["Wilson 95% CI", "이항비율 신뢰구간", "작은 표본의 점수 불확실성", "구간이 좁을수록 안정", "이벤트 8건 같은 소표본에 필수"],
            ],
            columns=["지표", "정의/계산", "무엇을 보는가", "방향", "PPT 해석 주의"],
        )

        # 1) 이상탐지 확장 평가: 현재 output/anomaly_metrics.csv와 동일한 time split 계약
        anomaly_scores = read_csv(REPO / "output/anomaly_scores.csv")
        anomaly_method_columns = {
            "Isolation Forest 정책": ("iforest_anomaly_label", "iforest_anomaly_score"),
            "Mahalanobis 정책": ("mahalanobis_anomaly_label", "mahalanobis_score"),
            "IF·Mahalanobis 결합": ("anomaly_label", "anomaly_score"),
            "강한 q99 결합": ("strong_anomaly_label", "anomaly_score"),
            "지속성 criticality 결합": ("anomaly_event_label", "anomaly_score"),
        }
        anomaly_extended_rows = []
        for split in ["validation", "holdout"]:
            part = anomaly_scores[anomaly_scores["split_time_based"].eq(split)]
            y_true = part["label"].eq("pre_fault").astype(int)
            for name, (prediction_column, score_column) in anomaly_method_columns.items():
                row = {"모델/정책": name, "검증구간": split}
                row.update(binary_metrics(y_true, part[prediction_column], part[score_column]))
                anomaly_extended_rows.append(row)
        anomaly_extended = pd.DataFrame(anomaly_extended_rows)

        # 2) Risk 확장 평가: 분류는 risk_score+운영 level, 보정은 base risk_probability로 분리
        risk_scores = read_csv(REPO / "output/risk_scores.csv")
        risk_extended_rows = []
        for split in ["train", "validation", "holdout"]:
            part = risk_scores[risk_scores["split_event_regime_based"].eq(split)]
            y_true = part["label"].eq("pre_fault").astype(int)
            y_pred = part["risk_high_or_critical"].astype(int)
            row = {"현재 모델": risk_meta["model_version"], "검증구간": split}
            row.update(binary_metrics(y_true, y_pred, part["risk_score"]))
            probability = np.clip(part["risk_probability"].astype(float), 1e-6, 1 - 1e-6)
            row.update(
                {
                    "Base확률_Brier": brier_score_loss(y_true, probability),
                    "Base확률_LogLoss": log_loss(y_true, probability, labels=[0, 1]),
                    "Base확률_ECE10": binary_ece(y_true, probability),
                }
            )
            risk_extended_rows.append(row)
        risk_extended = pd.DataFrame(risk_extended_rows)

        risk_subgroup_rows = []
        risk_holdout_raw = risk_scores[risk_scores["split_event_regime_based"].eq("holdout")]
        for group_column in ["season_bucket", "configuration_type"]:
            for group_value, part in risk_holdout_raw.groupby(group_column, dropna=False):
                y_true = part["label"].eq("pre_fault").astype(int)
                row = {"그룹기준": group_column, "그룹": group_value}
                row.update(binary_metrics(y_true, part["risk_high_or_critical"], part["risk_score"]))
                risk_subgroup_rows.append(row)
        risk_subgroup = pd.DataFrame(risk_subgroup_rows)

        # 3) Leadtime 확장 평가: 실제 pre_fault 행만 사용
        lead_scores = read_csv(REPO / "output/leadtime_scores.csv")
        bucket_labels = ["0-24h", "1-3d", "3-7d"]
        bucket_to_index = {name: index for index, name in enumerate(bucket_labels)}
        probability_columns = ["leadtime_prob_0-24h", "leadtime_prob_1-3d", "leadtime_prob_3-7d"]
        leadtime_extended_rows = []
        leadtime_class_rows = []
        for split in ["train", "validation", "holdout"]:
            part = lead_scores[
                lead_scores["label"].eq("pre_fault")
                & lead_scores["split_event_regime_based"].eq(split)
            ].copy()
            y_true = part["lead_time_bucket"].map(bucket_to_index).astype(int).to_numpy()
            y_pred = part["predicted_lead_time_bucket"].map(bucket_to_index).astype(int).to_numpy()
            probabilities = part[probability_columns].astype(float).to_numpy()
            probabilities = np.clip(probabilities, 1e-12, 1.0)
            probabilities = probabilities / probabilities.sum(axis=1, keepdims=True)
            distance = y_pred - y_true
            row = {
                "현재 모델": lead_meta["model_version"],
                "검증구간": split,
                "표본수": len(part),
                "정확도": accuracy_score(y_true, y_pred),
                "균형정확도": balanced_accuracy_score(y_true, y_pred),
                "Macro_F1": sk_f1_score(y_true, y_pred, average="macro", zero_division=0),
                "Weighted_F1": sk_f1_score(y_true, y_pred, average="weighted", zero_division=0),
                "Top2_정확도": top_k_accuracy_score(y_true, probabilities, k=2, labels=[0, 1, 2]),
                "Bucket_MAE": np.abs(distance).mean(),
                "Bucket_RMSE": np.sqrt(np.mean(distance ** 2)),
                "인접구간이내비율": (np.abs(distance) <= 1).mean(),
                "평균_부호오차": distance.mean(),
                "조기예측률": (distance < 0).mean(),
                "지연예측률": (distance > 0).mean(),
                "Multiclass_Brier": np.mean(np.sum((probabilities - np.eye(3)[y_true]) ** 2, axis=1)),
                "Multiclass_LogLoss": log_loss(y_true, probabilities, labels=[0, 1, 2]),
                "Confidence_ECE10": confidence_ece(y_true, y_pred, probabilities.max(axis=1)),
            }
            leadtime_extended_rows.append(row)

            precision, recall, f1_values, support = precision_recall_fscore_support(
                y_true, y_pred, labels=[0, 1, 2], zero_division=0
            )
            for index, bucket in enumerate(bucket_labels):
                leadtime_class_rows.append(
                    {
                        "검증구간": split, "실제구간": bucket, "표본수": int(support[index]),
                        "정밀도": precision[index], "재현율": recall[index], "F1": f1_values[index],
                    }
                )
        leadtime_extended = pd.DataFrame(leadtime_extended_rows)
        leadtime_class_metrics = pd.DataFrame(leadtime_class_rows)

        # 4) Priority 확장 평가: 현재 183행 holdout 계약, 후보는 별도 표시
        priority_extended_rows = []
        active_rows = active_priority_eval[
            active_priority_eval["split"].eq("holdout")
            & active_priority_eval["metric_scope"].eq("row")
        ]
        policy_names = {
            "current_best_priority": "현재 Rule body",
            "m1_specialist_priority": "M1 specialist 단독",
            "legacy_priority": "rollback v1 0.65/0.35·82.5/95.0",
            "m1_hybrid_priority": "요청 v2 0.72/0.28·67.5/82.5",
            "m1_evidence_priority": "이전 v3 pre-event 0.99 OR leadtime 0.97",
            "m1_risk_pre_event_priority": "공식 v4 Risk 0.78 OR pre-event 0.99",
        }
        event_rows = active_priority_eval[
            active_priority_eval["split"].eq("holdout")
            & active_priority_eval["metric_scope"].eq("fault_event")
        ].set_index("policy")
        for _, source in active_rows.iterrows():
            metrics = binary_metrics(
                np.r_[np.ones(int(source["tp"] + source["fn"])), np.zeros(int(source["fp"] + source["tn"]))],
                np.r_[np.ones(int(source["tp"])), np.zeros(int(source["fn"])), np.ones(int(source["fp"])), np.zeros(int(source["tn"]))],
            )
            metrics.update(
                {
                    "설정": policy_names[source["policy"]],
                    "후보상태": "공식" if source["policy"] == "m1_risk_pre_event_priority" else ("rollback" if source["policy"] == "legacy_priority" else "비교 기준"),
                    "고장이벤트": int(event_rows.loc[source["policy"], "fault_events"]),
                    "탐지이벤트": int(event_rows.loc[source["policy"], "detected_fault_events"]),
                    "이벤트재현율": float(event_rows.loc[source["policy"], "fault_event_recall"]),
                }
            )
            priority_extended_rows.append(metrics)
        priority_extended = pd.DataFrame(priority_extended_rows)[
            ["설정", "후보상태", "표본수", "양성수", "TP", "FP", "FN", "TN", "정확도", "균형정확도",
             "정밀도", "재현율", "특이도", "음성예측도_NPV", "F1", "MCC", "Cohen_Kappa", "오경보율_FPR",
             "알람률", "고장이벤트", "탐지이벤트", "이벤트재현율"]
        ]

        topk_source = read_csv(paths["priority_lgbm_topk"])
        priority_topk = topk_source[
            topk_source["split"].eq("holdout")
            & topk_source["model_key"].isin(["rule_based", "lgbm_priority_only"])
        ][["model", "k_label", "n", "pre_fault_count", "precision_pre_fault", "recall_pre_fault", "ndcg_graded"]].copy()
        priority_topk.insert(0, "계약", "상위 current-best 366행 holdout")
        priority_topk = priority_topk.rename(
            columns={
                "model": "모델", "k_label": "K", "n": "전체표본", "pre_fault_count": "양성표본",
                "precision_pre_fault": "Precision_at_K", "recall_pre_fault": "Recall_at_K", "ndcg_graded": "NDCG_at_K",
            }
        )

        operational_ranking = read_csv(paths["upstream_ranking"])
        operational_priority_topk = operational_ranking[
            operational_ranking["score"].eq("priority_score")
        ][["k", "total_pre_fault_rows", "total_fault_events", "precision_at_k", "row_recall_at_k", "event_recall_at_k", "urgent_recall_at_k", "ndcg_at_k"]].copy()
        operational_priority_topk.insert(0, "계약", "상위 운영 holdout 300행·10이벤트")

        # 5) 점수 분포 이동: train을 기준으로 holdout 비교
        drift_specs = [
            ("이상탐지", anomaly_scores, "split_time_based", None, "anomaly_score"),
            ("Risk base probability", risk_scores, "split_event_regime_based", None, "risk_probability"),
            ("Risk 운영 score", risk_scores, "split_event_regime_based", None, "risk_score"),
            ("Leadtime confidence", lead_scores, "split_event_regime_based", lead_scores["label"].eq("pre_fault"), "predicted_lead_time_confidence"),
        ]
        drift_rows = []
        for model_name, frame, split_column, filter_mask, score_column in drift_specs:
            scoped = frame if filter_mask is None else frame[filter_mask]
            reference = scoped.loc[scoped[split_column].eq("train"), score_column]
            comparison = scoped.loc[scoped[split_column].eq("holdout"), score_column]
            ks = ks_2samp(reference.dropna(), comparison.dropna())
            psi = population_stability_index(reference, comparison)
            drift_rows.append(
                {
                    "모델/점수": model_name, "기준표본_train": reference.notna().sum(), "비교표본_holdout": comparison.notna().sum(),
                    "train평균": reference.mean(), "holdout평균": comparison.mean(), "PSI": psi,
                    "KS통계량": ks.statistic, "KS_p값": ks.pvalue,
                    "판정": "큰 이동" if psi >= 0.25 else ("주의" if psi >= 0.10 else "PSI 안정"),
                }
            )
        score_drift = pd.DataFrame(drift_rows)

        # 6) 핵심 비율의 95% 신뢰구간: 점추정만 제시하지 않도록 별도 표기
        risk_holdout_metrics = risk_extended[risk_extended["검증구간"].eq("holdout")].iloc[0]
        lead_holdout_part = lead_scores[
            lead_scores["label"].eq("pre_fault")
            & lead_scores["split_event_regime_based"].eq("holdout")
        ]
        lead_y = lead_holdout_part["lead_time_bucket"].map(bucket_to_index).astype(int).to_numpy()
        lead_pred = lead_holdout_part["predicted_lead_time_bucket"].map(bucket_to_index).astype(int).to_numpy()
        lead_probs = lead_holdout_part[probability_columns].to_numpy()
        lead_top2_correct = 0
        for actual, probabilities in zip(lead_y, lead_probs):
            lead_top2_correct += int(actual in np.argsort(probabilities)[-2:])
        uncertainty_inputs = [
            ["이상탐지 IF·Mahalanobis", "정밀도", 38, 46],
            ["이상탐지 IF·Mahalanobis", "재현율", 38, 77],
            ["이상탐지 IF·Mahalanobis", "오경보율", 8, 106],
            ["복원 Risk", "정밀도", int(risk_holdout_metrics["TP"]), int(risk_holdout_metrics["TP"] + risk_holdout_metrics["FP"])],
            ["복원 Risk", "재현율", int(risk_holdout_metrics["TP"]), int(risk_holdout_metrics["TP"] + risk_holdout_metrics["FN"])],
            ["복원 Risk", "오경보율", int(risk_holdout_metrics["FP"]), int(risk_holdout_metrics["FP"] + risk_holdout_metrics["TN"])],
            ["복원 Leadtime", "정확도", int((lead_y == lead_pred).sum()), len(lead_y)],
            ["복원 Leadtime", "Top-2 정확도", int(lead_top2_correct), len(lead_y)],
            ["Priority 공식 v4", "정밀도", int(official_row["tp"]), int(official_row["tp"] + official_row["fp"])],
            ["Priority 공식 v4", "재현율", int(official_row["tp"]), int(official_row["tp"] + official_row["fn"])],
            ["Priority 공식 v4", "오경보율", int(official_row["fp"]), int(official_row["fp"] + official_row["tn"])],
            ["Priority 공식 v4", "이벤트 재현율", int(official_event["detected_fault_events"]), int(official_event["fault_events"])],
            ["Agent V1", "보고서 성공률", 5, 7],
            ["Agent V1", "출력 재생성 발생률", 3, 7],
        ]
        uncertainty_rows = []
        for subject, metric, successes, total in uncertainty_inputs:
            low, high = wilson_interval(successes, total)
            uncertainty_rows.append(
                {
                    "대상": subject, "지표": metric, "성공건": successes, "분모": total,
                    "점추정": successes / total, "95%CI_하한": low, "95%CI_상한": high,
                    "PPT표기": f"{successes / total * 100:.1f}% ({successes}/{total}, 95% CI {low * 100:.1f}~{high * 100:.1f}%)",
                }
            )
        uncertainty = pd.DataFrame(uncertainty_rows)

        # 7) 현재 프로젝트 설정/실험 기준과 발표용 권고 기준을 의도적으로 분리
        validation_guardrails = pd.DataFrame(
            [
                ["현재 설정", "Agent evidence", "근거충분성", ">= 0.75", "backend settings", "현재 코드값"],
                ["현재 설정", "모델 점수 대조", "UI/API 허용 오차", "<= 0.12", "backend settings", "현재 코드값"],
                ["현재 설정", "Answer quality", "Judge 점수", ">= 75/100", "backend settings", "기능 기본 비활성"],
                ["현재 설정", "RAG", "JSONL top score", ">= 6.0", "backend settings", "기능 기본 비활성"],
                ["현재 설정", "RAG", "고유 match 수", ">= 2", "backend settings", "기능 기본 비활성"],
                ["공식 v4", "Priority Risk/pre-event gate", "현재 결과의 이벤트 재현율", "0.875 (7/8)", "재현 실행 결과", "표본이 작아 신규 이벤트에서 계속 감시"],
                ["공식 v4", "Priority Risk/pre-event gate", "현재 결과의 FPR", "0.1038", "재현 실행 결과", "균형 F1 최상, 장기 목표 0.05는 미달"],
                ["PPT/PoC 권고", "Risk", "재현율 / FPR", ">= 0.80 / <= 0.05", "운영비용 기반 제안", "프로젝트 확정 계약 아님"],
                ["PPT/PoC 권고", "Risk", "ROC-AUC / AP", ">= 0.70 / 기존 대비 +0.05", "분리·불균형 성능 제안", "프로젝트 확정 계약 아님"],
                ["PPT/PoC 권고", "Risk", "Brier / ECE", "<= 0.20 / <= 0.05", "확률 보정 제안", "프로젝트 확정 계약 아님"],
                ["PPT/PoC 권고", "Leadtime", "Macro-F1 / Top-2", ">= 0.60 / >= 0.90", "구간분류 제안", "프로젝트 확정 계약 아님"],
                ["PPT/PoC 권고", "Leadtime", "Bucket MAE / 지연예측률", "<= 0.40 / <= 0.10", "운영 안전 제안", "프로젝트 확정 계약 아님"],
                ["PPT/PoC 권고", "Priority", "이벤트 재현율 / FPR", ">= 0.90 / <= 0.05", "알람 운영 제안", "이벤트 30건 이상 재검증 권장"],
                ["PPT/PoC 권고", "Priority", "정밀도 / median lead", ">= 0.80 / >= 24h", "출동효율·선행시간 제안", "프로젝트 확정 계약 아님"],
                ["PPT/PoC 권고", "Agent", "보고서 성공률 / task 완료율", ">= 0.95 / >= 0.90", "운영 안정성 제안", "V2 실측 필요"],
                ["PPT/PoC 권고", "Agent", "근거충실도 / 무근거 주장률", ">= 0.90 / <= 0.02", "LLM 품질 제안", "사람평가셋 필요"],
                ["PPT/PoC 권고", "Agent", "p95 지연 / p95 비용", "<= 90초 / <= $0.05", "SLO 제안", "실제 트래픽에서 조정"],
            ],
            columns=["구분", "대상", "평가기준", "기준값", "근거", "주의"],
        )

        additional_validation = pd.DataFrame(
            [
                ["시간 일반화", "Walk-forward/rolling split", "월별 순차 학습-다음 기간 평가", "부분 가능", "현재 로컬 동일 계약 rolling 재실험 필요", "최우선"],
                ["이벤트 일반화", "Untouched event holdout", "임계값 선택에 사용하지 않은 고장이벤트", "미실시", "공식 v4 validation 이벤트가 3건뿐이라 신규 검증 필요", "최우선"],
                ["설비 일반화", "Leave-one-substation-out", "기계실 1곳씩 완전 제외", "가능", "substation 컬럼 존재", "높음"],
                ["제조사 일반화", "Leave-one-manufacturer-out", "미관측 제조사 외부검증", "불가", "현재 데이터 manufacturer 1만 존재", "높음"],
                ["구성 일반화", "설비 구성별 성능", "SH+DHW / sub-circuit 분리", "계산 완료", "Risk subgroup CSV 제공", "높음"],
                ["계절 일반화", "계절별 성능", "겨울·봄·여름·가을 분리", "계산 완료", "Risk subgroup CSV 제공", "높음"],
                ["고장 유형", "Fault-type event recall", "누수·펌프·밸브 등 유형별 이벤트", "추가 가능", "유형별 이벤트 수가 작아 CI 필수", "높음"],
                ["결측 강건성", "센서 결측 주입", "5/10/20/30% block missing", "미실시", "재현 가능한 corruption test 필요", "높음"],
                ["노이즈 강건성", "센서 잡음·spike 주입", "표준편차 0.5/1/2배 및 outlier", "미실시", "물리 허용범위 보존 필요", "높음"],
                ["임계값 민감도", "Threshold/weight sweep", "Risk·Priority 성능곡선", "부분 완료", "hybrid sweep 존재; untouched 검증 필요", "최우선"],
                ["확률 보정", "Reliability/Brier/ECE", "예측확률의 의미 검증", "계산 완료", "Risk/Leadtime CSV 제공", "높음"],
                ["분포 이동", "PSI/KS", "train-holdout 점수 이동", "계산 완료", "score drift CSV 제공", "높음"],
                ["통계 불확실성", "Bootstrap/Wilson CI", "점수 95% 신뢰구간", "부분 완료", "핵심 비율 Wilson CI 제공; event bootstrap 추가 권장", "높음"],
                ["통계 비교", "McNemar/DeLong", "후보 간 차이의 유의성", "미실시", "동일 행 예측쌍과 충분한 표본 필요", "중간"],
                ["운영 알람", "False episodes/site-month", "연속 오경보를 에피소드로 묶어 월 환산", "상위 계약만 존재", "현재 로컬 M1 동일 계약 재산출 필요", "높음"],
                ["선행시간", "첫 알람 lead time", "median/p10/mean 및 24h·3d recall", "상위 계약만 존재", "현재 로컬 M1 동일 계약 재산출 필요", "높음"],
                ["용량 제한", "Precision/Recall/NDCG@K", "일일 처리 가능량 K별 평가", "계산 완료", "두 개의 서로 다른 holdout 계약 분리", "높음"],
                ["V2 Agent", "실제 1사이클 호출·비용·시간", "단계별 p50/p95와 재실행", "미실시", "DB에 V2 실행 표본 없음", "최우선"],
                ["LLM 정확성", "Groundedness/claim support", "문장별 근거 연결", "미실시", "한글 사람평가셋 필요", "최우선"],
                ["사용자 효율", "승인율·수정률·편집거리", "작업지시서 초안의 사람 수정량", "미실시", "UI 이벤트 로깅 필요", "높음"],
            ],
            columns=["영역", "검증", "방법", "현재상태", "필요조건/한계", "우선순위"],
        )

        agent_quality_criteria = pd.DataFrame(
            [
                ["완료성", "Task completion rate", "요청된 단계와 필수 필드가 모두 생성된 비율", "자동+사람평가", "현재 미계측"],
                ["정확성", "Groundedness", "보고서 주장 중 모델·센서·RAG 근거로 지지되는 비율", "문장별 라벨", "현재 미계측"],
                ["안전성", "Unsupported claim rate", "근거 없이 원인·조치를 단정한 문장 비율", "문장별 라벨", "현재 미계측"],
                ["검색", "Citation precision", "인용 근거 중 실제 주장과 관련된 비율", "RAG 평가셋", "RAG quality 기본 비활성"],
                ["검색", "Citation coverage", "검증 필요 주장 중 근거가 붙은 비율", "RAG 평가셋", "RAG quality 기본 비활성"],
                ["대화", "Intent hit rate", "수정·확정·취소 의도를 올바르게 분류한 비율", "한글 대화 테스트셋", "현 적중률 정량 로그 없음"],
                ["사람검토", "First-pass acceptance", "수정 없이 바로 승인된 초안 비율", "UI 승인 이벤트", "현재 미계측"],
                ["사람검토", "Normalized edit distance", "초안 대비 최종본 수정량", "텍스트 diff", "현재 미계측"],
                ["안정성", "Report success rate", "보고서 단계가 정상 완료된 비율", "실행 로그", "V1 실측 5/7=71.4%"],
                ["안정성", "Regeneration rate", "출력 파싱·품질 문제로 재생성한 비율", "실행 로그", "V1 출력 재생성 3/7=42.9%"],
                ["성능", "Latency p50/p95", "전체 및 단계별 응답시간 분위수", "실행 로그", "현재 7건이라 범위·평균 중심"],
                ["비용", "Cost p50/p95", "한 사이클·재생성·검토 대화별 비용", "token+공식단가", "nano 사용량 누락"],
                ["효율", "Tokens per accepted report", "승인 보고서 1건당 총 토큰", "실행+승인 로그", "현재 미계측"],
                ["복구", "Checkpoint reuse rate", "전체 재실행 대신 실패 단계만 재사용한 비율", "V2 task 로그", "V2 실측 없음"],
                ["결정성", "Idempotency", "같은 snapshot 재실행 시 핵심 판정이 유지되는 비율", "반복실험", "현재 미계측"],
            ],
            columns=["품질축", "KPI", "정의", "필요 데이터", "현재 상태"],
        )

        extended_tables = {
            "11_model_evaluation_metric_definitions_ko.csv": metric_definitions,
            "12_anomaly_extended_metrics_ko.csv": anomaly_extended,
            "13_risk_extended_metrics_ko.csv": risk_extended,
            "14_risk_subgroup_holdout_ko.csv": risk_subgroup,
            "15_leadtime_extended_metrics_ko.csv": leadtime_extended,
            "16_leadtime_class_metrics_ko.csv": leadtime_class_metrics,
            "17_priority_extended_metrics_ko.csv": priority_extended,
            "18_priority_topk_holdout_ko.csv": priority_topk,
            "18b_priority_operational_topk_ko.csv": operational_priority_topk,
            "19_score_drift_train_holdout_ko.csv": score_drift,
            "20_uncertainty_key_metrics_ko.csv": uncertainty,
            "21_validation_guardrails_ko.csv": validation_guardrails,
            "22_additional_validation_backlog_ko.csv": additional_validation,
            "23_agent_quality_validation_criteria_ko.csv": agent_quality_criteria,
        }
        for filename, frame in extended_tables.items():
            frame.to_csv(
                PPT_TABLE_DIR / filename,
                index=False,
                encoding="utf-8-sig",
                float_format="%.6f",
                lineterminator="\n",
            )

        display(Markdown("### 이상탐지 확장 성능"))
        display(anomaly_extended.round(4))
        display(Markdown("### Risk 확장 성능과 확률 보정"))
        display(risk_extended.round(4))
        display(Markdown("### Leadtime 확장 성능"))
        display(leadtime_extended.round(4))
        display(Markdown("### Priority 확장 성능"))
        display(priority_extended.round(4))
        display(Markdown("### 점수 분포 이동"))
        display(score_drift.round(4))
        display(Markdown("### 핵심 지표 95% 신뢰구간"))
        display(uncertainty)
        """
    ),
    md(
        """
        ## 부록 C. 확장 수치 해석 원칙

        1. Risk의 `ROC-AUC/AP`는 최종 운영 점수인 `risk_score`, Brier·Log-loss·ECE는 확률 의미가 있는
           `risk_probability`로 계산했다. 두 컬럼의 목적이 다르므로 하나의 확률처럼 섞지 않는다.
        2. Leadtime의 부호오차는 `예측 index - 실제 index`다. 양수는 실제보다 늦은 구간으로 예측한 것으로,
           운영 대응을 늦출 수 있어 조기 예측보다 위험하게 본다.
        3. Priority의 183행 M1 holdout, 366행 Rule/LGBM holdout, 300행 운영 holdout은 서로 다른 계약이다.
           같은 차트 안에 그리더라도 표본·라벨·split을 반드시 표시한다.
        4. PSI와 KS는 원인 진단이 아니라 이동 경보다. 이동이 크면 어떤 계절·설비·센서가 원인인지 추가 분석한다.
        5. `8/8=100%`도 이벤트 수가 8건이면 95% 신뢰구간이 넓다. 점추정만으로 승격하지 않는다.
        """
    ),
    md(
        """
        ## 부록 D. 최종 승격 체크리스트

        - [ ] 모델 파일·score CSV·Agent Card의 SHA256과 행/열 계약 고정
        - [ ] 동일한 event/time split에서 이전 모델과 후보 비교
        - [ ] 임계값·가중치는 validation에서만 선택
        - [ ] untouched event holdout과 rolling split에서 재검증
        - [ ] Risk FPR cap과 hybrid guardrail을 동시에 통과
        - [ ] task/activity gate는 native label 확보 전 독립 성능 주장 금지
        - [ ] 도메인 이동(XAI mock)에서 오경보가 급증하면 승격 중단
        - [ ] Agent RAG/answer-quality 기능의 실제 feature flag 상태를 발표에 반영

        ### 최종 판정

        현재 구조에서 방어 가능한 주장은 다음과 같다.

        1. 상위 모델 계열 선택과 Rule-based priority 유지 결정은 비교 실험으로 지지된다.
        2. 검증된 handoff Risk·Leadtime artifact를 복원했고, 동일 M1 계약에서 Risk FPR 4.7%와 Leadtime macro-F1 69.3%를 재현했다.
        3. 공식 Priority v4는 `Risk >= 0.78 OR pre-event >= 0.99`이다. 작은 validation event 표본 때문에 신규 event/rolling 감시와 v2 보수 정책 비교가 필요하다.
        4. Agent 구성은 실제 코드 기준 9단계이며, 사람 검토와 단계별 추적성을 포함한다.
        """
    ),
]

OUT.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, OUT)
print(OUT)
