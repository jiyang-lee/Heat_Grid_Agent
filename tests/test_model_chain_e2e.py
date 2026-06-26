import json
from pathlib import Path

import pandas as pd
import pytest

from agent.model_chain.run_model_chain import run as run_model_chain
from agent.preprocessing.audit_predist_labels import audit_predist_label_distribution
from agent.priority.run_priority import run as run_priority

ZIP_PATH = Path("C:/Users/Admin/Downloads/predist_dataset.zip")
PREPROCESSED_PATH = Path("agent/fixtures/preprocessing/predist_sample/output/preprocessed_windows_sample.csv")
LABELS_PATH = Path("agent/fixtures/preprocessing/predist_sample/output/supervised_window_labels.csv")

pytestmark = pytest.mark.filterwarnings(
    "ignore:Setting the shape on a NumPy array has been deprecated:DeprecationWarning"
)


def test_predist_label_audit_matches_full_zip_ratio():
    if not ZIP_PATH.exists():
        return

    audit = audit_predist_label_distribution(ZIP_PATH)

    assert audit.normal_windows == 1818
    assert audit.pre_fault_windows == 1528
    assert audit.lead_bucket_counts == {"0-24h": 217, "1-3d": 436, "3-7d": 875}


def test_model_chain_and_priority_e2e(tmp_path):
    model_chain_output = tmp_path / "model_chain_output.csv"
    feature_report = tmp_path / "feature_adapter_report.json"
    priority_output = tmp_path / "priority_scores.csv"

    chain = run_model_chain(
        preprocessed_path=PREPROCESSED_PATH,
        labels_path=LABELS_PATH,
        dst=model_chain_output,
        report_path=feature_report,
    )
    priority = run_priority(src=model_chain_output, dst=priority_output)
    report = json.loads(feature_report.read_text(encoding="utf-8"))

    assert len(chain) == 300
    assert len(priority) == 300
    assert pd.read_csv(model_chain_output).shape[0] == 300
    assert pd.read_csv(priority_output).shape[0] == 300

    assert chain["label"].value_counts().to_dict() == {"normal": 163, "pre_fault": 137}
    assert chain[chain["label"].eq("pre_fault")]["lead_time_bucket"].value_counts().to_dict() == {
        "3-7d": 79,
        "1-3d": 39,
        "0-24h": 19,
    }

    assert report["anomaly"]["requested_features"] == 195
    assert report["risk"]["requested_features"] == 189
    assert report["leadtime"]["requested_features"] == 221
    assert set(priority["priority_level"]).issubset({"low", "medium", "high", "urgent"})
