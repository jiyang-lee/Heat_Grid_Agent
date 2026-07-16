"""Tests for blinded pairwise RAG comparison utilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from compare_pairwise_passes import merge_passes
from run_pairwise_rag_judge import build_pairwise_cases, build_summary, normalize_result


def generation(case_id: str, answer: str) -> dict:
    return {"case_id": case_id, "generated_answer": answer, "cited_chunk_ids": []}


class PairwiseRagJudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = [{
            "case_id": "case-1",
            "query": "question",
            "answerable": True,
            "expected_answer_points": ["point"],
            "forbidden_claims": [],
            "retrieved_contexts": [{"chunk_id": "chunk-1", "text": "evidence"}],
            "category": "fault_cause",
            "query_intent": "fault_cause",
            "query_type": "keyword_match",
            "difficulty": "easy",
        }]
        self.retrieval = [{"case_id": "case-1", "metrics": {"hit_rate_at_5": 1, "mrr": 1, "ndcg_at_5": 1}}]

    def test_build_cases_blinds_condition_labels(self):
        cases = build_pairwise_cases(
            [generation("case-1", "with")],
            [generation("case-1", "without")],
            self.dataset,
            self.retrieval,
        )
        self.assertEqual(len(cases), 1)
        self.assertNotIn("with_rag", cases[0]["payload"])
        self.assertNotIn("no_rag", cases[0]["payload"])
        self.assertEqual(set(cases[0]["candidate_mapping"].values()), {"with_rag", "no_rag"})

    def test_normalization_maps_winner_back_to_condition(self):
        case = build_pairwise_cases(
            [generation("case-1", "with")],
            [generation("case-1", "without")],
            self.dataset,
            self.retrieval,
        )[0]
        scores = {
            "correctness": 5,
            "completeness": 5,
            "actionability": 5,
            "evidence_grounding": 5,
            "calibration": 5,
            "expected_point_coverage": 1.0,
            "unsupported_claim_risk": "NONE",
            "failure_tags": ["none"],
        }
        winner_letter = next(key for key, value in case["candidate_mapping"].items() if value == "with_rag")
        record = normalize_result(
            case,
            {
                "candidate_a": scores,
                "candidate_b": scores,
                "overall_winner": winner_letter,
                "winner_strength": "CLEAR",
                "review_priority": "LOW",
                "reason": "better",
            },
            "judge-model",
            {},
        )
        self.assertEqual(record["winner"], "with_rag")
        self.assertEqual(record["retrieval_effect"], "beneficial")

    def test_summary_contains_dimension_and_segment_breakdowns(self):
        record = {
            "winner": "with_rag",
            "winner_strength": "clear",
            "retrieval_effect": "beneficial",
            "failure_signal": "none",
            "review_priority": "LOW",
            "with_rag": {**{field: 5 for field in ("correctness", "completeness", "actionability", "evidence_grounding", "calibration")}, "expected_point_coverage": 1.0, "unsupported_claim_risk": "NONE", "failure_tags": ["none"]},
            "no_rag": {**{field: 2 for field in ("correctness", "completeness", "actionability", "evidence_grounding", "calibration")}, "expected_point_coverage": 0.2, "unsupported_claim_risk": "NONE", "failure_tags": ["over_abstention"]},
            "metadata": {"retrieval_hit_at_5": True, "category": "fault_cause", "difficulty": "easy", "query_intent": "fault_cause"},
            "judge_metadata": {"usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
        }
        summary = build_summary([record], [], "judge-model", 1)
        self.assertEqual(summary["winner_counts"]["with_rag"], 1)
        self.assertEqual(summary["dimension_averages"]["correctness"]["delta_with_minus_without"], 3)
        self.assertEqual(summary["breakdown_by_retrieval_hit"]["True"]["with_rag_win_rate"], 1)

    def test_swapped_positions_reverse_candidate_mapping(self):
        normal = build_pairwise_cases(
            [generation("case-1", "with")],
            [generation("case-1", "without")],
            self.dataset,
            self.retrieval,
        )[0]
        swapped = build_pairwise_cases(
            [generation("case-1", "with")],
            [generation("case-1", "without")],
            self.dataset,
            self.retrieval,
            swap_positions=True,
        )[0]
        self.assertEqual(normal["candidate_mapping"]["A"], swapped["candidate_mapping"]["B"])

    def test_opposite_pass_winners_are_contested(self):
        def pass_row(winner: str) -> dict:
            values = {**{field: 4 for field in ("correctness", "completeness", "actionability", "evidence_grounding", "calibration")}, "expected_point_coverage": 0.8}
            return {
                "case_id": "case-1",
                "winner": winner,
                "with_rag": values,
                "no_rag": values,
                "metadata": {"retrieval_hit_at_5": True, "category": "fault_cause", "difficulty": "easy"},
                "review_priority": "LOW",
                "reason": "reason",
            }
        records, summary = merge_passes([pass_row("with_rag")], [pass_row("no_rag")])
        self.assertEqual(records[0]["consensus_winner"], "contested")
        self.assertEqual(records[0]["review_priority"], "HIGH")
        self.assertEqual(summary["position_sensitive_count"], 1)


if __name__ == "__main__":
    unittest.main()
