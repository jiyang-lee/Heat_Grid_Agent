# Answer Generation Runner

This runner prepares HeatGrid Answer Evaluation outputs without reusing existing Agent Output samples.

## Scope

- Input dataset: `rag_evaluation/answer_evaluation/answer_eval.draft.jsonl`
- Output target: `rag_evaluation/results/answer_generation_pilot.jsonl`
- Dataset status: `draft`
- Result level: `reference`
- Official benchmark: `false`
- Retrieval backend: `jsonl`

## Modes

```powershell
python rag_evaluation/scripts/run_answer_generation.py --dry-run
python rag_evaluation/scripts/run_answer_generation.py --pilot
python rag_evaluation/scripts/run_answer_generation.py --case-id retrieval_eval_001
python rag_evaluation/scripts/run_answer_generation.py --all
```

`--all` is implemented but should not be run until the 5-case pilot has been reviewed.

## Input Leakage Policy

The generation prompt receives only `query`, `retrieved_contexts`, minimal case metadata, and safety rules.

The runner excludes evaluation labels and answers from generation input:

- `expected_answer_points`
- `relevant_chunk_ids`
- `partially_relevant_chunk_ids`
- `forbidden_claims`
- `human_scores`
- `automated_scores`
- `label_status`
- evaluation results

## API Configuration

API keys must be provided through `.env` or environment variables. The key is never printed.

Supported environment variables:

- `OPENAI_API_KEY`
- `HEATGRID_OPENAI_MODEL`
- `OPENAI_MODEL`

The default model in the config is `gpt-5.4-mini`, resolved from `HEATGRID_OPENAI_MODEL` or `OPENAI_MODEL` when available.

## Citation Validation

`cited_chunk_ids` must be a subset of the retrieved `chunk_id` values for the case. `document_id`, document titles, source files, pages, or section names are not accepted as citation IDs.
