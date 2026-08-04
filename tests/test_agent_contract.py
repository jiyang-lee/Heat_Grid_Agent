from __future__ import annotations

import hashlib
import json
import unittest

import pandas as pd

from src.third_model import config


class AgentContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.agent = pd.read_csv(config.AGENT_CARD_PATH).copy()
        cls.priority = pd.read_csv(config.PRIORITY_SCORES_PATH).copy()

    def test_agent_columns_match_contract(self) -> None:
        self.assertEqual(config.AGENT_OUTPUT_COLUMNS, list(self.agent.columns))

    def test_agent_has_no_excluded_experiment_fields(self) -> None:
        excluded_columns = [
            column
            for column in self.agent.columns
            if column.startswith(config.EXCLUDED_EXPERIMENT_PREFIXES)
        ]
        self.assertEqual([], excluded_columns)

    def test_agent_has_no_rejected_reference_fields(self) -> None:
        rejected = [
            column
            for column in self.agent.columns
            if column == "hybrid_anomaly_confidence"
        ]
        self.assertEqual([], rejected)

    def test_agent_priority_is_m1_risk_pre_event_gate_v4(self) -> None:
        self.assertTrue("priority_source" in self.agent.columns)
        sources = set(self.agent["priority_source"].astype(str).unique())
        self.assertEqual({config.M1_PRIORITY_SOURCE}, sources)
        self.assertEqual({config.M1_PRIORITY_POLICY_VERSION}, set(self.agent["policy_version"].astype(str)))
        self.assertTrue(pd.to_numeric(self.agent["current_best_weight"], errors="coerce").isna().all())
        self.assertTrue(pd.to_numeric(self.agent["m1_specialist_weight"], errors="coerce").isna().all())
        max_delta = (
            pd.to_numeric(self.agent["priority_score"], errors="coerce")
            - pd.to_numeric(self.agent["m1_risk_pre_event_priority_score"], errors="coerce")
        ).abs().max()
        self.assertLessEqual(float(max_delta), 1e-9)
        self.assertTrue(
            (self.agent["priority_level"].astype(str) == self.agent["m1_risk_pre_event_priority_level"].astype(str)).all()
        )
        score = pd.to_numeric(self.agent["priority_score"], errors="coerce")
        expected_level = pd.Series(
            pd.Categorical(
                pd.cut(
                    score,
                    bins=[float("-inf"), config.M1_RISK_PRE_EVENT_MEDIUM_THRESHOLD, config.M1_RISK_PRE_EVENT_HIGH_THRESHOLD, config.M1_RISK_PRE_EVENT_URGENT_THRESHOLD, float("inf")],
                    labels=["low", "medium", "high", "urgent"],
                    right=False,
                ),
                categories=["low", "medium", "high", "urgent"],
            ),
            index=self.agent.index,
        ).astype(str)
        self.assertTrue((self.agent["priority_level"].astype(str) == expected_level).all())
        expected_high = (
            pd.to_numeric(self.agent["risk_score"], errors="coerce").ge(config.M1_RISK_HIGH_THRESHOLD)
            | pd.to_numeric(self.agent["m1_specialist_pre_event_probability"], errors="coerce").ge(config.M1_PRE_EVENT_HIGH_THRESHOLD)
        )
        actual_high = self.agent["priority_level"].astype(str).isin(["high", "urgent"])
        self.assertTrue((actual_high == expected_high).all())

    def test_agent_key_is_unique(self) -> None:
        duplicate_count = int(self.agent.duplicated(config.KEY_COLUMNS).sum())
        self.assertEqual(0, duplicate_count)

    def test_agent_is_m1_only(self) -> None:
        manufacturers = set(self.agent["manufacturer"].astype(str).unique())
        self.assertEqual({config.M1_MANUFACTURER}, manufacturers)

    def test_agent_text_fields_are_populated(self) -> None:
        for column in ["why_reason", "recommended_action"]:
            empty_count = int(self.agent[column].fillna("").eq("").sum())
            self.assertEqual(0, empty_count, f"{column} has empty rows")

    def test_priority_rows_survive_into_agent_card(self) -> None:
        merged = self.priority.merge(
            self.agent[config.KEY_COLUMNS].drop_duplicates(),
            on=config.KEY_COLUMNS,
            how="left",
            indicator=True,
        )
        missing_count = int(merged["_merge"].eq("left_only").sum())
        self.assertEqual(0, missing_count)

    def test_active_package_outputs_exist(self) -> None:
        for path in [
            config.TRAINABLE_WINDOWS_PATH,
            config.FEATURE_COLUMNS_PATH,
            config.IMPUTATION_VALUES_PATH,
            config.ANOMALY_SCORES_PATH,
            config.ANOMALY_METRICS_PATH,
            config.ANOMALY_METADATA_PATH,
            config.ANOMALY_SCALER_PATH,
            config.IFOREST_MODEL_PATH,
            config.MAHALANOBIS_MODEL_PATH,
            config.RISK_SCORES_PATH,
            config.LEADTIME_SCORES_PATH,
            config.PRIORITY_SCORES_PATH,
            config.MERGED_SCORES_PATH,
            config.AGENT_CARD_PATH,
            config.STATE_CARD_SCHEMA_PATH,
            config.M1_SPECIALIST_GATE_SCORES_PATH,
            config.M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH,
            config.M1_SPECIALIST_GATE_METADATA_PATH,
            config.M1_SPECIALIST_SCORES_PATH,
            config.M1_SPECIALIST_AGENT_CARD_PATH,
            config.M1_RISK_PRE_EVENT_GATE_SWEEP_PATH,
            config.M1_SPECIALIST_COMPARISON_PATH,
            config.M1_SPECIALIST_REPORT_PATH,
            config.M1_SCOPE_REPORT_PATH,
        ]:
            self.assertTrue(path.exists(), f"missing active package artifact: {path}")

    def test_validated_risk_and_leadtime_artifact_hashes_match_metadata(self) -> None:
        for model_path, metadata_path in [
            (config.RISK_MODEL_PATH, config.RISK_METADATA_PATH),
            (config.LEADTIME_MODEL_PATH, config.LEADTIME_METADATA_PATH),
        ]:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            actual = hashlib.sha256(model_path.read_bytes()).hexdigest()
            self.assertEqual(metadata["artifact_sha256"].lower(), actual)


if __name__ == "__main__":
    unittest.main()
