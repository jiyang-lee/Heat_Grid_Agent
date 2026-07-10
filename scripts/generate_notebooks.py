from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"


def nb(cells: list[dict], path: Path) -> None:
    notebook = nbf.v4.new_notebook()
    notebook["cells"] = cells
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, path)


def md(text: str):
    return nbf.v4.new_markdown_cell(text)


def code(text: str):
    return nbf.v4.new_code_cell(text)


HEADER = """from pathlib import Path

def find_project_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src" / "third_model").exists():
            return candidate
    raise FileNotFoundError("M1 specialist repository root not found")

ROOT = find_project_root()
"""


def main() -> None:
    notebooks = {
        "00_raw_data_load.ipynb": [
            md(
                "# 00 Raw 데이터 확인\n\n"
                "원천 raw 폴더, 파일 목록, schema 요약을 확인한다. "
                "이 단계에서는 모델을 학습하지 않고 데이터 출처와 구조만 점검한다."
            ),
            code(HEADER + "\nfrom third_model.data_io import build_raw_inventory\ninventory = build_raw_inventory()\ninventory.head()"),
            code("inventory['file_type'].value_counts()"),
        ],
        "01_window_dataset_import.ipynb": [
            md(
                "# 01 Window 데이터셋 Import\n\n"
                "현재 best 프로젝트에서 만든 canonical `trainable_windows.csv`를 M1-only 기준으로 가져온다. "
                "feature list와 imputation value도 M1 train row 기준으로 다시 만든다."
            ),
            code(HEADER + "\nfrom third_model.data_io import import_canonical_windows\nwindows = import_canonical_windows()\nwindows.shape"),
            code("windows[['manufacturer','substation_id','window_start','window_end','label']].head()"),
        ],
        "02_anomaly_baseline.ipynb": [
            md(
                "# 02 Anomaly Baseline\n\n"
                "Mahalanobis + IsolationForest anomaly 구조를 재현한다. "
                "정상 train 분포 기준 score ratio와 criticality를 만든다."
            ),
            code(HEADER + "\nfrom third_model.anomaly import train_score_anomaly\nanomaly = train_score_anomaly()\nanomaly.shape"),
            code("anomaly[['manufacturer','substation_id','window_end','iforest_score_ratio','mahalanobis_score_ratio','anomaly_event_label']].head()"),
        ],
        "03_current_best_agent.ipynb": [
            md(
                "# 03 Current-best Agent\n\n"
                "기존 best risk/leadtime/priority 결과를 bridge하고, 운영용 agent card를 만든다."
            ),
            code(
                HEADER
                + "\nfrom third_model.best_bridge import materialize_current_best_model_artifacts, materialize_best_scores, build_merged_model_scores\n"
                + "from third_model.operational import build_agent_card\n"
                + "materialize_current_best_model_artifacts()\n"
                + "materialize_best_scores()\n"
                + "merged = build_merged_model_scores()\n"
                + "agent = build_agent_card()\n"
                + "merged.shape, agent.shape"
            ),
            code("agent[['manufacturer','substation_id','window_end','risk_level_calibrated','priority_level','recommended_action']].head()"),
        ],
        "04_m1_specialist_parallel.ipynb": [
            md(
                "# 04 M1 Specialist 병렬 근거\n\n"
                "M1 specialist gate 점수와 current best priority를 결합해 최종 M1 hybrid priority를 만든다."
            ),
            code(
                HEADER
                + "\nfrom third_model.m1_specialist import build_m1_specialist_outputs\n"
                + "m1 = build_m1_specialist_outputs()\n"
                + "m1.shape"
            ),
            code("import pandas as pd\npd.read_csv(ROOT / 'output/reports/m1_specialist_vs_current_best_comparison.csv')"),
            code("pd.read_csv(ROOT / 'output/agent/m1_agent_priority_card.csv').head()"),
        ],
        "05_validation.ipynb": [
            md(
                "# 05 검증\n\n"
                "최종 agent contract, row reconciliation, threshold sweep, active policy ablation을 검증한다."
            ),
            code(
                HEADER
                + "\nfrom third_model.validation import run_all_validations\n"
                + "run_all_validations()"
            ),
            code("import pandas as pd\npd.read_csv(ROOT / 'output/reports/ablation_summary.csv')"),
            code("pd.read_csv(ROOT / 'output/reports/row_reconciliation.csv')"),
        ],
        "06_agent_contract_review.ipynb": [
            md(
                "# 06 Agent 계약 점검\n\n"
                "agent에게 넘길 최종 column을 점검한다. "
                "`m1_specialist_*`는 active 근거 컬럼이다."
            ),
            code(HEADER + "\nimport pandas as pd\nagent = pd.read_csv(ROOT / 'output/agent_priority_card.csv')\nagent.columns.tolist()"),
            code("from third_model import config\nblocked = [c for c in agent.columns if c.startswith(config.EXCLUDED_EXPERIMENT_PREFIXES) or c == 'hybrid_anomaly_confidence']\nblocked"),
            code("pd.read_csv(ROOT / 'output/agent/agent_card_column_dictionary_ko.csv')"),
        ],
        "07_deploy_runbook.ipynb": [
            md(
                "# 07 배포 Runbook\n\n"
                "`deploy.py`로 agent handoff CSV를 다시 생성한다."
            ),
            code(
                HEADER
                + "\nfrom pathlib import Path\nfrom third_model.deploy import export_agent_columns\n"
                + "agent = export_agent_columns(ROOT / 'output/agent_priority_card.csv')\n"
                + "agent.shape"
            ),
        ],
    }
    for old in NOTEBOOK_DIR.glob("*.ipynb"):
        old.unlink()
    for name, cells in notebooks.items():
        nb(cells, NOTEBOOK_DIR / name)
        print(NOTEBOOK_DIR / name)


if __name__ == "__main__":
    main()
