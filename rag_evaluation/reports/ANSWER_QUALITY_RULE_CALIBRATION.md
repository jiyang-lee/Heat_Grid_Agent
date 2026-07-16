# Answer Quality Rule Calibration

## Scope

- Unique operational cases: 100
- Production RAG searches: 100
- RAG backend: PostgreSQL `pgvector` (112 indexed chunks)
- Actual answer texts: 200 (100 initial and 100 regenerated)
- Original versus regenerated comparisons: 200
- Candidate answer observations: 400
- Case and answer model: `gpt-5.4-mini`
- Independent Judge: `gpt-5.4`
- Evaluation passes: original order and swapped order
- Policy version: `answer-quality-policy.v2-100-rag-single-judge-draft`
- Status: Draft/Reference

Each Korean operator question is sent through the production `RagSearcher` with
the `pgvector` backend explicitly required. The initial and regenerated answers
receive exactly the same retrieved Top-5. Gold expected points and forbidden
claims are hidden from answer generation and are available only to the Judge.

## Retrieval Result

| Item | Result |
| --- | ---: |
| Top-5 gold hit | 25 |
| Top-5 gold miss | 75 |
| Overall Hit@5 | 25.00% |
| Answerable-case Hit@5 | 27.78% (25/90) |
| Retrieval errors | 0 |
| Backend fallback | 0 |

The low hit rate is part of the measured baseline, not repaired by injecting
gold evidence. It indicates that the current hash-embedding pgvector index has
weak Korean-query to mixed Korean/English-document retrieval performance.

## Dataset Distribution

| Item | Count |
| --- | ---: |
| Answerable | 90 |
| Unanswerable | 10 |
| Easy | 26 |
| Medium | 27 |
| Hard | 47 |
| Inspection action | 31 |
| Safety caution | 21 |
| Operating standard | 20 |
| Fault cause | 11 |
| Priority reason | 4 |
| Similar case | 3 |

## Answer Comparison Result

| Item | Result |
| --- | ---: |
| Regenerated wins | 141 |
| Original wins | 9 |
| Ties | 50 |
| Cross-validated threshold | 75 |
| Threshold stability range | 72-75 |
| Out-of-fold accuracy | 94.75% |
| Bad-answer capture rate | 95.60% |
| False-pass rate | 4.40% |
| Unnecessary regeneration rate | 5.81% |

For RAG-hit cases, regenerated/original/tie outcomes were 34/4/12. For RAG-miss
cases they were 107/5/38. Regeneration improves evidence-limitation language and
removes unsupported claims, but it cannot recover a missing gold document.

## Validated Rules

Rules require at least three triggered observations and at least 90% precision
for identifying a Judge-labeled bad answer.

| Rule | Support | Bad-answer precision |
| --- | ---: | ---: |
| Correctness <= 2 | 114 | 97.37% |
| Evidence grounding <= 2 | 23 | 100% |
| Over-abstention | 13 | 100% |
| Unsupported-claim risk MEDIUM/HIGH | 54 | 100% |

Citation mismatch triggered 15 times but reached only 73.33% bad-answer
precision. It remains a recorded reason, not a standalone hard gate.

## Judge Stability

- Candidate PASS/REGENERATE agreement: 177/200, or 88.50%
- Pairwise winner agreement: 72/100, or 72.00%
- Mean absolute score difference: 5.28 points
- Maximum absolute score difference: 28 points

The two Judge passes are used only for offline position-bias and policy-stability
analysis. Runtime does not average repeated judgments. Each candidate answer is
judged once.

## Runtime Policy

- Passing threshold: 75
- Quality evaluations per candidate: 1
- Maximum regeneration count: 1
- Failed first RAG answer: regenerate once and judge the revised answer once
- Selection: prefer the non-hard-failed answer, then the higher score
- Tie or regression: keep the original answer
- Storage: existing report stage snapshot and run event JSON
- New database table or column: none

## Limitations

The 100 questions are synthetic operational scenarios grounded in the curated
HeatGrid corpus. Retrieval is real production pgvector retrieval, and all answer
and Judge calls use the OpenAI API. Labels remain LLM-produced and require
operator sampling before this Draft/Reference policy becomes a release SLA.
