from __future__ import annotations

import pandas as pd
import pytest

from agent.io import paths
from agent.priority import contracts, rule_baseline
from agent.priority.run_priority import run as run_priority


def _row(**overrides) -> dict:
    row = {
        "manufacturer": "manufacturer 1",
        "substation_id": 1,
        "window_start": "2026-06-26T00:00:00+00:00",
        "window_end": "2026-06-26T06:00:00+00:00",
        "anomaly_score": 0.5,
        "risk_score": 50.0,
        "risk_probability": 0.5,
        "risk_level_calibrated": "high",
        "predicted_lead_time_bucket": "1-3d",
        "predicted_lead_time_confidence": 0.9,
        "leadtime_prob_0-24h": 0.2,
        "leadtime_prob_1-3d": 0.7,
        "leadtime_prob_3-7d": 0.1,
        "lead_time_bucket_distance": 1,
        "days_since_last_fault_event": 10.0,
        "days_since_last_task_event": 999.0,
        "days_since_last_any_event": 999.0,
    }
    row.update(overrides)
    return row


def test_high_risk_imminent_anomaly_scores_urgent():
    row = pd.Series(
        _row(
            anomaly_score=1.0,
            risk_probability=1.0,
            risk_level_calibrated="critical",
            predicted_lead_time_bucket="0-24h",
            predicted_lead_time_confidence=0.95,
        )
    )

    score = rule_baseline.score_row(row)

    assert score == pytest.approx(80.0)
    assert rule_baseline.level_frame(pd.Series([score])).iloc[0] == "urgent"


def test_recent_event_history_reduces_priority_score():
    base_score = rule_baseline.score_row(pd.Series(_row()))
    recent_score = rule_baseline.score_row(
        pd.Series(
            _row(
                days_since_last_task_event="3.0",
                days_since_last_any_event="3.0",
            )
        )
    )

    assert recent_score == pytest.approx(base_score - 13.0)


def test_run_priority_does_not_require_priority_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRIORITY_MODEL_PATH", tmp_path / "missing.joblib")
    src = tmp_path / "model_chain_output.csv"
    dst = tmp_path / "priority_scores.csv"
    pd.DataFrame(
        [
            _row(
                anomaly_score=1.0,
                risk_probability=1.0,
                risk_level_calibrated="critical",
                predicted_lead_time_bucket="0-24h",
                predicted_lead_time_confidence=0.95,
            )
        ]
    ).to_csv(src, index=False)

    out = run_priority(src=src, dst=dst)

    assert dst.exists()
    assert len(out) == 1
    assert out.loc[0, "priority_score"] == pytest.approx(80.0)
    assert out.loc[0, "priority_level"] == "urgent"
    assert out.loc[0, "model_version"] == contracts.MODEL_VERSION
