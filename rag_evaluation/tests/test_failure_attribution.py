"""Failure-origin classification tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from failure_attribution import classify_case, summarize_attributions


def automatic(**overrides):
    rule = {
        "json_valid": True,
        "error_count": 0,
        "citation_valid": True,
        "forbidden_claim_detected": False,
        "internal_label_leak_detected": False,
        "retrieval_miss_policy_passed": None,
        "answerable_policy_passed": None,
    }
    rule.update(overrides)
    return {"rule_evaluation": rule}


def judge(**overrides):
    row = {
        "overall_recommendation": "PASS",
        "hallucination_severity": "NONE",
        "faithfulness": 5,
        "operational_usefulness": 5,
        "citation_accuracy_semantic": 5,
        "answer_relevance": 5,
        "judge_confidence": "HIGH",
    }
    row.update(overrides)
    return row


class FailureAttributionTests(unittest.TestCase):
    def test_hit_and_good_answer_has_no_failure(self):
        result = classify_case(
            {"case_id": "hit-pass", "answerable": True, "retrieval_hit_at_5": True},
            automatic(),
            judge(),
        )
        self.assertEqual(result["retrieval_status"], "hit")
        self.assertEqual(result["generation_status"], "passed")
        self.assertEqual(result["failure_origin"], "none")

    def test_hit_and_bad_answer_is_generation_failure(self):
        result = classify_case(
            {"case_id": "hit-fail", "answerable": True, "retrieval_hit_at_5": True},
            automatic(),
            judge(overall_recommendation="FAIL", faithfulness=1),
        )
        self.assertEqual(result["failure_origin"], "generation")
        self.assertEqual(result["generation_status"], "failed")

    def test_miss_and_safe_abstention_is_retrieval_failure(self):
        result = classify_case(
            {"case_id": "miss-safe", "answerable": True, "retrieval_hit_at_5": False},
            automatic(retrieval_miss_policy_passed=True),
            judge(),
        )
        self.assertEqual(result["failure_origin"], "retrieval")
        self.assertTrue(result["safe_abstention"])

    def test_miss_and_unsupported_answer_is_mixed_failure(self):
        result = classify_case(
            {"case_id": "miss-fail", "answerable": True, "retrieval_hit_at_5": False},
            automatic(retrieval_miss_policy_passed=False),
            judge(hallucination_severity="MAJOR"),
        )
        self.assertEqual(result["failure_origin"], "mixed")
        self.assertEqual(result["generation_status"], "failed")

    def test_unanswerable_safe_abstention_is_not_failure(self):
        result = classify_case(
            {"case_id": "unanswerable", "answerable": False, "retrieval_hit_at_5": False},
            automatic(answerable_policy_passed=True),
            judge(),
        )
        self.assertEqual(result["retrieval_status"], "not_applicable")
        self.assertEqual(result["failure_origin"], "none")

    def test_revise_is_review_not_hard_failure(self):
        result = classify_case(
            {"case_id": "revise", "answerable": True, "retrieval_hit_at_5": True},
            automatic(),
            judge(overall_recommendation="REVISE", operational_usefulness=2),
        )
        self.assertEqual(result["generation_status"], "needs_review")
        self.assertEqual(result["failure_origin"], "generation")
        self.assertTrue(result["human_review_required"])

    def test_summary_counts_origins(self):
        records = [
            {"case_id": "1", "failure_origin": "none", "generation_status": "passed", "retrieval_status": "hit", "safe_abstention": False, "human_review_required": False},
            {"case_id": "2", "failure_origin": "retrieval", "generation_status": "passed", "retrieval_status": "miss", "safe_abstention": True, "human_review_required": True},
        ]
        summary = summarize_attributions(records)
        self.assertEqual(summary["failure_origin_counts"]["none"], 1)
        self.assertEqual(summary["failure_origin_counts"]["retrieval"], 1)
        self.assertEqual(summary["human_review_case_ids"], ["2"])


if __name__ == "__main__":
    unittest.main()
