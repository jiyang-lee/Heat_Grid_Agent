"""Retrieval baseline regression gate tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from baseline_gate import evaluate_baseline_gate


def baseline() -> dict:
    return {
        "baseline_id": "test-baseline",
        "retrieval": {
            "failed_case_count": 0,
            "macro_average_metrics": {
                "recall_at_5": 0.4,
                "hit_rate_at_5": 0.4,
                "mrr": 0.3,
                "ndcg_at_5": 0.29,
            },
        },
    }


def summary(**metrics: float) -> dict:
    values = {
        "recall_at_5": 0.4,
        "hit_rate_at_5": 0.4,
        "mrr": 0.3,
        "ndcg_at_5": 0.29,
    }
    values.update(metrics)
    return {"failed_case_count": 0, "macro_average_metrics": values}


class BaselineGateTests(unittest.TestCase):
    def test_equal_metrics_pass(self):
        result = evaluate_baseline_gate(summary(), baseline())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["failed_metrics"], [])

    def test_improved_metrics_pass(self):
        result = evaluate_baseline_gate(summary(recall_at_5=0.5, mrr=0.4), baseline())
        self.assertEqual(result["status"], "passed")

    def test_lower_metric_is_regression(self):
        result = evaluate_baseline_gate(summary(recall_at_5=0.39), baseline())
        self.assertEqual(result["status"], "regression")
        self.assertIn("recall_at_5", result["failed_metrics"])

    def test_retrieval_errors_are_regression(self):
        current = summary()
        current["failed_case_count"] = 1
        result = evaluate_baseline_gate(current, baseline())
        self.assertEqual(result["status"], "regression")
        self.assertIn("failed_case_count", result["failed_metrics"])


if __name__ == "__main__":
    unittest.main()
