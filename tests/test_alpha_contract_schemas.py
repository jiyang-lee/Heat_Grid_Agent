import json
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator

from agent.model_chain.feature_adapter import build_feature_matrix, load_feature_list
from agent.model_chain.run_model_chain import ANOMALY_META, LEADTIME_META, RISK_META


SCHEMA_DIR = Path("schema/json")
FEATURE_CONTRACT = Path("data/processed/ml_features/agent_feature_contract.json")
RAW_CONTRACT = Path("data/processed/ml_features/agent_required_raw_columns.json")
PREPROCESSED_FIXTURE = Path("agent/fixtures/preprocessing/predist_sample/output/preprocessed_windows_sample.csv")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema(name: str) -> dict:
    return _json(SCHEMA_DIR / name)


def test_alpha_contract_json_schemas_are_valid():
    for path in SCHEMA_DIR.glob("*.schema.json"):
        Draft202012Validator.check_schema(_json(path))


def test_alpha_contract_counts_are_locked():
    raw_contract = _json(RAW_CONTRACT)
    feature_contract = _json(FEATURE_CONTRACT)

    assert raw_contract["counts"]["required_raw_operational_columns_count"] == 29
    assert "raw contract 29" in _schema("sensor_readings.schema.json")["description"]
    assert len(_schema("sensor_readings.schema.json")["properties"]) == 30
    assert len(_schema("preprocessed_windows.schema.json")["properties"]) == 211
    assert len(_schema("prepro_model_features.schema.json")["properties"]) == 195
    assert feature_contract["counts"]["selected_feature_count"] == 195
    assert len(_schema("model_input_if.schema.json")["properties"]) == 195
    assert len(_schema("model_input_lgbm_risk.schema.json")["properties"]) == 189
    assert len(_schema("model_input_lgbm_leadtime.schema.json")["properties"]) == 221


def test_prepro_schema_matches_selected_feature_contract():
    feature_contract = _json(FEATURE_CONTRACT)
    expected = [row["column_name"] for row in feature_contract["selected_feature_columns"]]
    schema = _schema("prepro_model_features.schema.json")

    assert list(schema["properties"]) == expected
    assert schema["required"] == expected


def test_model_input_schemas_match_handoff_metadata():
    cases = [
        ("model_input_if.schema.json", ANOMALY_META, "selected_feature_columns"),
        ("model_input_lgbm_risk.schema.json", RISK_META, "model_feature_columns"),
        ("model_input_lgbm_leadtime.schema.json", LEADTIME_META, "model_feature_columns"),
    ]

    for schema_name, metadata_path, key in cases:
        expected = load_feature_list(metadata_path, key)
        schema = _schema(schema_name)
        assert list(schema["properties"]) == expected
        assert schema["required"] == expected


def test_feature_adapter_builds_locked_model_input_matrices():
    preprocessed = pd.read_csv(PREPROCESSED_FIXTURE)
    base_context = preprocessed[["source_file", "substation_id", "window_start", "window_end"]].copy()

    if_features = load_feature_list(ANOMALY_META, "selected_feature_columns")
    if_matrix = build_feature_matrix(preprocessed, if_features)
    assert list(if_matrix.frame.columns) == list(_schema("model_input_if.schema.json")["properties"])
    assert if_matrix.report["requested_features"] == 195

    risk_features = load_feature_list(RISK_META, "model_feature_columns")
    risk_extra = base_context.assign(anomaly_score=0.0)
    risk_matrix = build_feature_matrix(preprocessed, risk_features, extra_columns=risk_extra)
    assert list(risk_matrix.frame.columns) == list(_schema("model_input_lgbm_risk.schema.json")["properties"])
    assert risk_matrix.report["requested_features"] == 189

    leadtime_features = load_feature_list(LEADTIME_META, "model_feature_columns")
    leadtime_extra = base_context.assign(anomaly_score=0.0, risk_probability=0.0, risk_score=0.0)
    leadtime_matrix = build_feature_matrix(preprocessed, leadtime_features, extra_columns=leadtime_extra)
    assert list(leadtime_matrix.frame.columns) == list(_schema("model_input_lgbm_leadtime.schema.json")["properties"])
    assert leadtime_matrix.report["requested_features"] == 221

    for schema_name, matrix in [
        ("model_input_if.schema.json", if_matrix),
        ("model_input_lgbm_risk.schema.json", risk_matrix),
        ("model_input_lgbm_leadtime.schema.json", leadtime_matrix),
    ]:
        validator = Draft202012Validator(_schema(schema_name))
        errors = [
            error.message
            for row in matrix.frame.head(5).to_dict(orient="records")
            for error in validator.iter_errors(row)
        ]
        assert errors == []
