# HeatGrid RAG API Pairwise Comparison

## Status

- Evaluation level: Draft/Reference
- Cases: 28 paired with-RAG/no-RAG answers
- Answer model: `gpt-5.4-mini`
- Independent pairwise Judge: `gpt-5.4`
- Judge calls: 56 (28 cases x 2 position-swapped passes)
- Total Judge tokens: 144,185
- API failures: 0
- Official benchmark: No. Human-approved labels are still required.

## Why This Comparison Was Added

The original independent LLM Judge scored each answer separately. That method
correctly showed that no-RAG answers were safe, but safe abstention received high
faithfulness and citation scores even when it did not answer an answerable
question. The pairwise evaluation therefore compares both answers against the
same expected points, forbidden claims, and evidence excerpts.

Candidate identity was hidden from the Judge. A/B positions were reversed in the
second pass. Opposite non-tie winners were marked `contested` instead of forcing a
winner.

## Headline Result

| Consensus result | Cases |
| --- | ---: |
| with-RAG | 26 |
| tie | 1 |
| contested | 1 |

- Winner stayed identical in 26/28 cases.
- Position-sensitive cases: `retrieval_eval_019`, `retrieval_eval_028`.
- The result means RAG is usually better than the current no-RAG abstention
  baseline. It does not mean the RAG answers are already good enough for
  production.

## Direct Quality Comparison

Scores are the mean of both position-swapped passes.

| Dimension | with-RAG | no-RAG | Delta |
| --- | ---: | ---: | ---: |
| Correctness (1-5) | 3.75 | 2.52 | +1.23 |
| Completeness (1-5) | 2.79 | 1.30 | +1.48 |
| Actionability (1-5) | 3.02 | 1.50 | +1.52 |
| Evidence grounding (1-5) | 3.57 | 1.75 | +1.82 |
| Calibration (1-5) | 4.70 | 4.32 | +0.38 |
| Expected-point coverage | 45.2% | 8.9% | +36.3%p |

The largest gain is evidence grounding, followed by actionability and
completeness. The main concern is absolute completeness: with-RAG covers only
45.2% of the Draft expected points on average.

## Retrieval Hit Versus Miss

| Top-5 retrieval | Cases | Consensus | with-RAG correctness | with-RAG actionability | with-RAG coverage |
| --- | ---: | --- | ---: | ---: | ---: |
| Hit | 10 | with-RAG 10 | 4.50 | 4.05 | 79.7% |
| Miss | 18 | with-RAG 16, tie 1, contested 1 | 3.33 | 2.44 | 26.0% |

This is the most important result. Retrieval success raises expected-point
coverage by 53.7 percentage points and actionability by 1.61 points. Many miss
cases still select with-RAG only because no-RAG over-abstains; their absolute
answer quality remains weak.

## Query Segment Findings

| Category | Cases | with-RAG coverage | with-RAG actionability | Note |
| --- | ---: | ---: | ---: | --- |
| similar_case | 2 | 82.5% | 3.75 | Strongest answerable category |
| safety_caution | 3 | 54.5% | 3.33 | One stable tie |
| fault_cause | 2 | 52.5% | 3.00 | Useful but incomplete |
| inspection_action | 7 | 40.6% | 3.00 | Retrieval-sensitive |
| operating_standard | 8 | 27.6% | 2.69 | Needs better document coverage |
| priority_reason | 3 | 19.7% | 2.17 | Weakest answerable category |
| unanswerable | 3 | 88.8% | 4.00 | Measures correct limitation, not factual answering |

Hard cases remain weak: 23.8% coverage, with-RAG 2 wins, 1 tie, and 1 contested
out of 4. Easy and medium cases had stable with-RAG wins, but medium coverage was
still only 43.6%.

## Safety Trade-off

- with-RAG unsupported-claim risk: `LOW` 21, `NONE` 7 in both passes.
- no-RAG unsupported-claim risk: `LOW` 13-14, `NONE` 14-15.
- Neither condition received `MEDIUM` or `HIGH` unsupported-claim risk.
- with-RAG citation mismatch appeared in 2-3 cases across the two passes.
- with-RAG missed expected points in 20-22 cases; no-RAG did so in 26-27 cases.
- with-RAG over-abstained in 8-11 cases; no-RAG did so in 22-24 cases.

RAG improves usefulness without creating a high-risk result in this Draft set,
but it introduces a modest increase in low-level unsupported-claim and citation
risk. This should remain part of the manual review form.

## Top-K Expansion Evidence

The current JSONL retrieval run produced:

| Retrieval depth | Cases with a relevant result | Rate |
| --- | ---: | ---: |
| Top-5 | 10/25 evaluable cases | 40% |
| Top-10 | 13/25 evaluable cases | 52% |
| Top-20 | 17/25 evaluable cases | 64% |

Among 15 answerable Top-5 misses, Top-10 recovered 3 cases and Top-20 recovered
7 cases. This supports the backend policy of expanding 5 -> 10 -> 20 only after
an insufficient-evidence review. Eight answerable misses still remain, so Top-K
expansion is not a replacement for query rewriting, qrel correction, or better
indexing/reranking.

## Cases Requiring Attention

- `retrieval_eval_006`: stable tie. Both answers missed all expected points and
  over-abstained. The relevant chunk appears by Top-20, so expanded rerun is a
  concrete candidate fix.
- `retrieval_eval_019`: position-sensitive (`tie` then with-RAG). Both original
  answers were incomplete; keep it in manual review.
- `retrieval_eval_028`: contested (`no-RAG` then with-RAG). It is an unanswerable
  hard case and should receive human judgment rather than an automatic winner.
- `retrieval_eval_002`: labeled as a Top-5 miss but achieved 100% expected-point
  coverage. Retrieved row 004 already contains the pump checks while the qrel
  names row 008. This is evidence that the relevant-chunk labels are too narrow,
  not simply that retrieval failed.

## Baseline Interpretation

Use both comparison views:

1. Independent scoring measures each condition's absolute safety and quality.
   It reported 17 improved, 7 degraded, and 4 tied cases by effectiveness delta.
2. Direct pairwise scoring measures which answer better serves the same query.
   Its two-pass consensus reported 26 with-RAG, 1 tie, and 1 contested case.

The difference is expected: the independent method rewards safe no-RAG
abstention, while the pairwise rubric explicitly penalizes over-abstention on
answerable questions.

For the current Draft baseline, track at least:

- Retrieval Recall/HitRate, MRR, and nDCG.
- Pairwise expected-point coverage, correctness, and actionability.
- Top-5-hit and Top-5-miss segments separately.
- Unsupported-claim risk and citation mismatch.
- Position-sensitive and human-review case counts.

The next quality step is to human-review the 14 pairwise `MEDIUM/HIGH` cases,
expand incomplete qrels such as `retrieval_eval_002`, and then freeze an approved
evaluation dataset. Only after that should these values become release-blocking
thresholds.

## Artifacts

- Runtime answer-quality baseline: `rag_evaluation/baselines/answer_quality_reference_v1.json`
- `rag_evaluation/results/pairwise_rag_judge_results.jsonl`
- `rag_evaluation/results/pairwise_rag_judge_results_swap.jsonl`
- `rag_evaluation/results/pairwise_rag_judge_consensus.jsonl`
- `rag_evaluation/results/pairwise_rag_judge_consensus_summary.json`
- `rag_evaluation/llm_judge/pairwise_rag_judge_prompt.md`
