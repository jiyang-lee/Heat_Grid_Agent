from __future__ import annotations

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

    def test_agent_priority_is_m1_hybrid(self) -> None:
        self.assertTrue("priority_source" in self.agent.columns)
        sources = set(self.agent["priority_source"].astype(str).unique())
        self.assertEqual({"m1_hybrid_current_best_0.65_m1_specialist_0.35"}, sources)
        max_delta = (
            pd.to_numeric(self.agent["priority_score"], errors="coerce")
            - pd.to_numeric(self.agent["m1_hybrid_priority_score"], errors="coerce")
        ).abs().max()
        self.assertLessEqual(float(max_delta), 1e-9)
        self.assertTrue(
            (self.agent["priority_level"].astype(str) == self.agent["m1_hybrid_priority_level"].astype(str)).all()
        )

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
            config.M1_SPECIALIST_COMPARISON_PATH,
            config.M1_SPECIALIST_REPORT_PATH,
            config.M1_SCOPE_REPORT_PATH,
        ]:
            self.assertTrue(path.exists(), f"missing active package artifact: {path}")


if __name__ == "__main__":
    unittest.main()
