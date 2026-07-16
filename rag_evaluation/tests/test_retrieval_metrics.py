"""Metric calculation validation for the standalone retrieval evaluator."""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from calculate_metrics import build_summary
from evaluate_case import evaluate_case
from evaluation_utils import extract_chunk_id, hit_rate_at_k, ndcg_at_k, precision_at_k, recall_at_k


TOLERANCE = 1e-9


def load_cases() -> list[dict]:
    with (ROOT / "tests" / "metric_test_cases.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


class RetrievalMetricTests(unittest.TestCase):
    def assertMetricAlmostEqual(self, actual, expected, metric_name: str) -> None:
        if expected is None:
            self.assertIsNone(actual, metric_name)
        else:
            self.assertIsNotNone(actual, metric_name)
            self.assertTrue(
                math.isclose(float(actual), float(expected), rel_tol=TOLERANCE, abs_tol=TOLERANCE),
                f"{metric_name}: expected {expected}, got {actual}",
            )

    def test_required_metric_cases(self) -> None:
        for fixture in load_cases():
            with self.subTest(fixture=fixture["name"]):
                result = evaluate_case(fixture["case"], fixture["retrieved_chunk_ids"])
                for metric_name, expected in fixture["expected_metrics"].items():
                    self.assertMetricAlmostEqual(result["metrics"][metric_name], expected, metric_name)
                expected_reason = fixture.get("expected_exclusion_reason")
                if expected_reason:
                    self.assertEqual(result["exclusion_reason"], expected_reason)
                    self.assertTrue(result["excluded_from_macro_metrics"])
                expected_warnings = set(fixture.get("expected_warnings", []))
                self.assertTrue(expected_warnings.issubset(set(result["warnings"])))

    def test_k_zero_or_negative_is_safe(self) -> None:
        retrieved = ["rel_a"]
        relevant = {"rel_a"}
        self.assertEqual(recall_at_k(retrieved, relevant, 0), 0.0)
        self.assertEqual(recall_at_k(retrieved, relevant, -1), 0.0)
        self.assertEqual(precision_at_k(retrieved, relevant, 0), 0.0)
        self.assertEqual(precision_at_k(retrieved, relevant, -1), 0.0)
        self.assertEqual(hit_rate_at_k(retrieved, relevant, 0), 0.0)
        self.assertEqual(hit_rate_at_k(retrieved, relevant, -1), 0.0)

    def test_unknown_chunk_ids_are_irrelevant_not_errors(self) -> None:
        fixture = {
            "case_id": "unknown_chunk",
            "query": "unknown",
            "category": "unit",
            "difficulty": "easy",
            "query_intent": "metric_validation",
            "answerable": True,
            "label_status": "draft",
            "review_required": True,
            "relevant_chunk_ids": ["rel_a"],
            "partially_relevant_chunk_ids": [],
        }
        result = evaluate_case(fixture, ["unknown_chunk_id"])
        self.assertEqual(result["metrics"]["recall_at_1"], 0.0)
        self.assertEqual(result["metrics"]["precision_at_1"], 0.0)
        self.assertEqual(result["metrics"]["hit_rate_at_1"], 0.0)
        self.assertEqual(result["metrics"]["mrr"], 0.0)

    def test_extract_chunk_id_does_not_fallback_to_document_id(self) -> None:
        self.assertEqual(extract_chunk_id({"chunk_id": "chunk_a", "document_id": "doc_a"}), "chunk_a")
        self.assertEqual(extract_chunk_id({"id": "chunk_b", "document_id": "doc_b"}), "chunk_b")
        with self.assertRaises(ValueError):
            extract_chunk_id({"document_id": "doc_only"})

    def test_relevant_partial_overlap_warns_and_partial_gain_is_excluded(self) -> None:
        fixture = {
            "case_id": "overlap_labels",
            "query": "overlap",
            "category": "unit",
            "difficulty": "medium",
            "query_intent": "metric_validation",
            "answerable": True,
            "label_status": "draft",
            "review_required": True,
            "relevant_chunk_ids": ["rel_a"],
            "partially_relevant_chunk_ids": ["rel_a", "part_a"],
        }
        result = evaluate_case(fixture, ["rel_a", "part_a"])
        self.assertIn("overlapping_relevant_partial_labels:rel_a", result["warnings"])
        self.assertMetricAlmostEqual(result["metrics"]["ndcg_at_5"], 1.0, "overlap_ndcg")
        self.assertMetricAlmostEqual(
            ndcg_at_k(["part_a"], {"rel_a"}, {"rel_a", "part_a"}, 5),
            0.38009376671593426,
            "partial_overlap_excluded_from_ideal",
        )

    def test_macro_average_and_breakdowns(self) -> None:
        fixtures = load_cases()
        results = [evaluate_case(item["case"], item["retrieved_chunk_ids"]) for item in fixtures]
        summary = build_summary(
            results,
            dataset_path="metric_test_cases.json",
            dataset_status="draft",
            result_level="reference",
            official_benchmark=False,
        )
        included = [row for row in results if not row["excluded_from_macro_metrics"]]
        expected_mrr = sum(row["metrics"]["mrr"] for row in included) / len(included)
        self.assertMetricAlmostEqual(summary["macro_average_metrics"]["mrr"], expected_mrr, "macro_mrr")
        self.assertEqual(summary["case_count"], 10)
        self.assertEqual(summary["evaluated_case_count"], 8)
        self.assertEqual(summary["excluded_unanswerable_count"], 1)
        self.assertIn("unit", summary["category_breakdown"])
        self.assertIn("hard", summary["difficulty_breakdown"])
        self.assertIn("metric_validation", summary["query_intent_breakdown"])

    def test_no_nan_or_infinity_in_summary_json(self) -> None:
        fixtures = load_cases()
        results = [evaluate_case(item["case"], item["retrieved_chunk_ids"]) for item in fixtures]
        summary = build_summary(results, "metric_test_cases.json", "draft", "reference", False)
        encoded = json.dumps(summary, allow_nan=False)
        self.assertNotIn("NaN", encoded)
        self.assertNotIn("Infinity", encoded)


if __name__ == "__main__":
    unittest.main()
