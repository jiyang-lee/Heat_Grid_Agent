"""with-RAG/no-RAG comparison tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from compare_rag_conditions import compare_conditions


def row(case_id: str, score: int, recommendation: str = "PASS") -> dict:
    return {
        "case_id": case_id,
        "faithfulness": score,
        "operational_usefulness": score,
        "citation_accuracy_semantic": score,
        "answer_relevance": score,
        "overall_recommendation": recommendation,
        "hallucination_severity": "NONE",
    }


class RagConditionComparisonTests(unittest.TestCase):
    def test_positive_delta_means_rag_improved(self):
        records, summary = compare_conditions([row("case-1", 5)], [row("case-1", 3)])
        self.assertTrue(records[0]["rag_effectiveness_improved"])
        self.assertEqual(summary["rag_effectiveness_improved_case_count"], 1)
        self.assertEqual(summary["average_score_deltas_with_minus_without"]["faithfulness"], 2)

    def test_missing_pair_marks_partial(self):
        _, summary = compare_conditions(
            [row("case-1", 5), row("case-2", 4)],
            [row("case-1", 3)],
        )
        self.assertEqual(summary["comparison_status"], "partial")
        self.assertEqual(summary["with_rag_only_case_ids"], ["case-2"])


if __name__ == "__main__":
    unittest.main()
