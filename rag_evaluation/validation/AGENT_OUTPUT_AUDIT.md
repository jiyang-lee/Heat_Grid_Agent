# Agent Output ?? ?? ??

## 1. ?? ??

HeatGrid ???? ?? ?? ????? ??? Agent Output JSON? ??? ???? ????. ?? ??? ??? ?? ??? Answer Evaluation? ??? ??? ?? ?? ????, ??? ?? ??? example, mock, seed, report generator ????? ???? ???.

??? ?? ??? ?? ????? ????. Agent, LLM, ??, Docker, DB? ???? ??? ?? ???? ??? ???? ???. ????? ???? ???.

## 2. ??? ??

????? ?? ?? ??? ????.

- `v0_ops_handoff_package/`
- `outputs/` ??: ?? ??
- `output/`
- `examples/` ??: ?? ?? ??, ??? ?? `examples/` ??
- `agent_runs/` ??: ?? ??
- `logs/` ??: ?? ??
- `simulator/`
- `data/`
- `docs/`

?? ?? ??? `rag_evaluation/validation/agent_output_inventory.json`? ????? ????.

## 3. ??? Agent Output ??

??:

| ?? | ? |
|---|---:|
| ??? ?? ? | 40 |
| Agent Output Contract full match | 18 |
| partial match ?? ?? ??? | 21 |
| ?? ?? ??? ??? ? | 0 |
| Answer Evaluation 28? case direct match | 0 |
| Answer Evaluation 28? case possible match | 0 |

Full match ??? `decision`, `summary`, `action_plan`, `caution`, `evidence` ? ?? ?? ??? ???. ?? full match?? ?? ?????? ??? actual run?? ?? ???.

## 4. ??/??/Mock/Seed ???

| # | file_path | classification | format | records | contract | card_id | run_id | timestamp | retrieved_ids | cited_ids | 28-case match | reuse |
|---:|---|---|---|---:|---|---|---|---|---|---|---|---|
| 1 | `v0_ops_handoff_package/examples/ops_agent_output.example.json` | example_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 2 | `v0_ops_handoff_package/contracts/ops_agent_output.schema.json` | schema_or_contract | json | 1 | partial | false | false | false | false | false | no_match | no |
| 3 | `v0_ops_handoff_package/input.json` | unknown | json | 1 | partial | true | false | false | false | false | no_match | format_only |
| 4 | `v0_ops_handoff_package/MANIFEST.json` | unknown | json | 1 | partial | false | false | true | false | false | no_match | format_only |
| 5 | `v0_ops_handoff_package/README.md` | unknown | md | 1 | partial | true | false | false | false | false | no_match | format_only |
| 6 | `v0_ops_handoff_package/AGENT_BRIEF.md` | unknown | md | 1 | partial | true | false | false | false | false | no_match | format_only |
| 7 | `v0_ops_handoff_package/RAG_HANDBOOK.md` | unknown | md | 1 | partial | true | false | false | false | false | no_match | format_only |
| 8 | `v0_ops_handoff_package/db/seed.sql` | seed_output | sql | 1 | partial | true | false | false | false | false | no_match | no |
| 9 | `v0_ops_handoff_package/queries/verify.sql` | seed_output | sql | 1 | no | false | false | false | false | false | no_match | no |
| 10 | `v0_ops_handoff_package/report_generator_hsj/outputs/ops_agent/ops_agent_output_sample.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 11 | `docs/contracts/ops_agent_result_v4.example.json` | example_output | json | 1 | partial | true | true | false | false | false | no_match | format_only |
| 12 | `docs/contracts/ops_agent_result_v4.md` | schema_or_contract | md | 1 | partial | true | true | false | false | false | no_match | no |
| 13 | `simulator/versions/v2_postgres_react_ops/contracts/ops_agent_output.schema.json` | schema_or_contract | json | 1 | partial | false | false | false | false | false | no_match | no |
| 14 | `output/ops_agent/cases/control_controller_urgent_no_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 15 | `output/ops_agent/cases/control_controller_urgent_with_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 16 | `output/ops_agent/cases/leakage_water_loss_high_no_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 17 | `output/ops_agent/cases/leakage_water_loss_high_with_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 18 | `output/ops_agent/cases/pressure_regulator_urgent_no_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 19 | `output/ops_agent/cases/pressure_regulator_urgent_with_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 20 | `output/ops_agent/cases/pump_failure_urgent_no_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 21 | `output/ops_agent/cases/pump_failure_urgent_with_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 22 | `output/ops_agent/cases/unknown_review_low_disagreement_no_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 23 | `output/ops_agent/cases/unknown_review_low_disagreement_with_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 24 | `output/ops_agent/cases/unknown_review_medium_disagreement_no_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 25 | `output/ops_agent/cases/unknown_review_medium_disagreement_with_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 26 | `output/ops_agent/cases/unknown_review_urgent_no_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 27 | `output/ops_agent/cases/unknown_review_urgent_with_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 28 | `output/ops_agent/cases/valve_actuator_high_no_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 29 | `output/ops_agent/cases/valve_actuator_high_with_rag.json` | mock_output | json | 1 | full | false | false | false | false | false | no_match | format_only |
| 30 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/acceptance_anomaly.mock.json` | mock_output | json | 1 | partial | false | false | true | false | false | no_match | format_only |
| 31 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/acceptance_daily.mock.json` | mock_output | json | 1 | partial | true | false | true | false | false | no_match | format_only |
| 32 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/anomaly_report.enriched_input.json` | unknown | json | 1 | partial | true | false | false | false | false | no_match | format_only |
| 33 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/anomaly_report.mock.json` | mock_output | json | 1 | partial | false | false | true | false | false | no_match | format_only |
| 34 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/anomaly_report.no_rag.llm.json` | unknown | json | 1 | partial | false | false | true | false | false | no_match | format_only |
| 35 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/anomaly_report.with_rag.llm.json` | unknown | json | 1 | partial | false | false | true | false | false | no_match | format_only |
| 36 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/daily_report.actual.2020-03-16.no_rag.llm.json` | unknown | json | 1 | partial | true | false | true | false | false | no_match | format_only |
| 37 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/daily_report.actual.2020-03-16.with_rag.llm.json` | unknown | json | 1 | partial | true | false | true | false | false | no_match | format_only |
| 38 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/daily_report.actual_input.2020-03-16.json` | unknown | json | 1 | partial | true | false | true | false | false | no_match | format_only |
| 39 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/daily_report.actual_input.2020-03-16.no_rag.json` | unknown | json | 1 | partial | true | false | true | false | false | no_match | format_only |
| 40 | `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/daily_report.mock.json` | mock_output | json | 1 | partial | true | false | true | false | false | no_match | format_only |

?? ??:

- `actual_run_output`: ?? Agent ?? ???? `run_id`, `card_id`, ?? ?? ? ?? provenance? ???? ??
- `example_output`: ?? ?? ?? ??? ??
- `mock_output`: ???/??/??? ??? ??? ??
- `seed_output`: DB ??? ?? ?????? seed
- `schema_or_contract`: JSON Schema ?? ?? ?? ??
- `unknown`: ??? ?? ????? ?? ?? ??? ??? ? ?? ??

## 5. v0_ops_handoff_package ?? ??

?? ?? ??? ??:

| ?? | ?? ?? | ?? |
|---|---|---|
| `v0_ops_handoff_package/examples/ops_agent_output.example.json` | v0 Agent Output Contract? full match??. `decision`, `summary`, `action_plan`, `caution`, `evidence`? ?? ??. | example_output |
| `v0_ops_handoff_package/contracts/ops_agent_output.schema.json` | v0 output schema?? ?? ??? ???. | schema_or_contract |
| `v0_ops_handoff_package/input.json` | `raw_context`, `priority_context`, `internal_context`? ?? `card_id`? ????? output? ???. | input/context only |
| `v0_ops_handoff_package/MANIFEST.json` | ??? ??? entrypoint ??. ?? ?? ??. | package metadata |
| `v0_ops_handoff_package/README.md` | ??? ?? ??. ?? ?? ??. | documentation |
| `v0_ops_handoff_package/AGENT_BRIEF.md` | Agent ??/?? ??. ?? ?? ??. | documentation |
| `v0_ops_handoff_package/RAG_HANDBOOK.md` | RAG ?? ??. ?? ?? ??. | documentation |
| `v0_ops_handoff_package/db/seed.sql` | `priority_cards`, `priority_decisions`, `model_outputs`, `sensor_summaries` seed? ??? `ops_agent_runs` ?? Agent Output record ??? ??. | seed_output, Agent Output ?? |
| `v0_ops_handoff_package/queries/verify.sql` | ?? ???? Agent Output record? ???. | seed/query support |
| `v0_ops_handoff_package/report_generator_hsj/outputs/ops_agent/ops_agent_output_sample.json` | v0 Agent Output Contract? full match??? sample ???? ?? provenance? ??. | mock_output |
| `v0_ops_handoff_package/report_generator_hsj/outputs/report_generator/*.json` | report generator mock/LLM/report input ?????. ?? `rag_evidence`? `priority_cards`? ??? Agent Output 28 case ??? ???. | report generator artifact |

`ops_agent_output.example.json`? ?? example?? ????. `seed.sql`?? priority card? ??/?? seed? ??? ?? Agent Output record? `ops_agent_runs` seed? ???? ???. `input.json`? output example? ?? ??? ????? ??? direct `card_id` ??? ???? ?????? output example ?? ??.

## 6. ?? Output Contract?? ?? ??

?? v0 Agent Output Contract ?? ??? ??? ??.

- `decision.priority`
- `decision.operator_review`
- `decision.data_quality`
- `summary`
- `action_plan`
- `caution`
- `evidence.priority_score`
- `evidence.current_best`
- `evidence.m1_specialist`
- `evidence.main_signals`
- `evidence.used_tools`

Full match ??? ? 18???.

- `v0_ops_handoff_package/examples/ops_agent_output.example.json`
- `v0_ops_handoff_package/report_generator_hsj/outputs/ops_agent/ops_agent_output_sample.json`
- `output/ops_agent/cases/control_controller_urgent_no_rag.json`
- `output/ops_agent/cases/control_controller_urgent_with_rag.json`
- `output/ops_agent/cases/leakage_water_loss_high_no_rag.json`
- `output/ops_agent/cases/leakage_water_loss_high_with_rag.json`
- `output/ops_agent/cases/pressure_regulator_urgent_no_rag.json`
- `output/ops_agent/cases/pressure_regulator_urgent_with_rag.json`
- `output/ops_agent/cases/pump_failure_urgent_no_rag.json`
- `output/ops_agent/cases/pump_failure_urgent_with_rag.json`
- `output/ops_agent/cases/unknown_review_low_disagreement_no_rag.json`
- `output/ops_agent/cases/unknown_review_low_disagreement_with_rag.json`
- `output/ops_agent/cases/unknown_review_medium_disagreement_no_rag.json`
- `output/ops_agent/cases/unknown_review_medium_disagreement_with_rag.json`
- `output/ops_agent/cases/unknown_review_urgent_no_rag.json`
- `output/ops_agent/cases/unknown_review_urgent_with_rag.json`
- `output/ops_agent/cases/valve_actuator_high_no_rag.json`
- `output/ops_agent/cases/valve_actuator_high_with_rag.json`

??? ? full match ???? ?? ?? ??? ????. ????? `run_id`, `generated_at/timestamp`, `retrieved_chunk_ids`, `cited_chunk_ids`? ?? ??? `card_id`? ??. ??? ?? ?? ???? ????? Answer ?? ??? ground truth ???? ????.

## 7. ?? Agent ?? ?? ?? ??

??: NO.

?? ?? ???? ?? Agent ?? ??? ??? ? ?? JSON? ???? ???. `output/ops_agent/cases/*_with_rag.json` ??? RAG ?? ?? ??(`rag_http_server`)? `evidence.used_tools`? ??? ??? ???, ?? ??? ?? actual run?? ?? ???.

- `run_id` ??
- `card_id` ??
- `generated_at` ?? timestamp ??
- ?? ?? ??? ???? event/artifact ID ??
- ??? chunk ID ?? citation ID ??

`daily_report.actual.*.llm.json`?? ???? `actual`? ??? report generator ???? ??. ?? ?? daily/anomaly report ???? v0 Agent Output Contract? ???, 28? Answer Evaluation case? generated answer? ?? ??? ? ??.

## 8. Answer Evaluation 28? case?? ?? ???

?? ????: `rag_evaluation/answer_evaluation/answer_eval.draft.jsonl`

??? ?? ??:

- `case_id`
- `query`
- `card_id`
- `substation_id`
- `fault_group`
- `run_id`
- `retrieved_chunk_ids`
- `timestamp`

??:

| ?? ?? | ?? | ?? |
|---|---:|---|
| direct_match | 0 | ?? `case_id` ?? ?? `query` ? ?? ?? ?? ?? |
| possible_match | 0 | ?? ?? ??? ??? ?? ??? ?? |
| no_match | 40 | ?? ???? output ?? ?? report ???? ? 28? case? ???? ?? |

??: `output/ops_agent/cases`? ????? `pump_failure`, `pressure_regulator`, `valve_actuator` ?? fault group ??? ???, Answer Evaluation 28? case? `case_id`, `query`, `retrieved_chunk_ids`, `retrieved_contexts`? ?? ???? ?? ??. ??? ?? ???? ???.

## 9. ??? ??? ??

?? ?? ?? Answer Generation Runner ?? ??? ???? ?? ??? ??? ? ??.

- `summary`
- `action_plan`
- `caution`
- `decision.priority`
- `decision.operator_review`
- `decision.data_quality`
- `evidence.priority_score`
- `evidence.current_best`
- `evidence.m1_specialist`
- `evidence.main_signals`
- `evidence.used_tools`

Report generator ??/????? ??? ??? ? ??.

- `priority_cards`
- `ops_evidence_list`
- `rag_evidence`
- `work_order_summaries`
- report ??? daily/anomaly report field layout

?? ? ??? ?? Answer Evaluation scoring? ?? ????, ?? ?? ?? schema? report integration ?? ????? ?? ?? ????.

## 10. ??? ??

?? ?? ?? ???? ??? ?? ?? ?? ??? ??? ??? ??.

| ?? ?? | ?? ?? ?? | ?? |
|---|---|---|
| `generated_answer` ?? `summary/action_plan/caution` | ?? ?? | v0 ?? output?? ??? ?? ?? ?? ?? |
| `card_id` ?? `query` ?? ?? | ??? ?? | v0 input?? `card_id`? ??? output example? ?? ???? ?? |
| `retrieved_chunk_ids` ?? `retrieved_context` | ?? | report enriched input?? `rag_evidence`? ??? 28? case? ?? ?? ?? |
| `cited_chunk_ids` | ?? | citation accuracy ?? ?? |
| model name | ?? | ??? ?? |
| prompt version | ?? | ??? ?? |
| `generated_at` | ?? report metadata?? ?? | Agent Output timestamp? ?? ??? |
| backend | ?? | with_rag/no_rag ??? ?? used_tools ??? ?? |
| `top_k` | ?? | Retrieval ?? ?? ?? |
| `run_id` | v4 example? ?? | ?? ?? run_id? ? ? ?? |

## 11. ?? Agent Output ??? ?? ??

?? ??: C. ??/Mock? ??.

??:

- v0 Contract full match output? ????.
- ??? actual run provenance? ??.
- 28? Answer Evaluation case? direct match?? ?? ??.
- retrieved chunk? citation ??? ?? Grounding, Faithfulness, Citation Accuracy ??? ?? ??? ? ??.
- ??? ?? ?? ??? ???? ?? ??? ??? ? ??.

??? ?? ??? ?? ???? ????.

- Answer Generation Runner? ?? ?? ??
- UI/report generator integration sample ??
- v0/v4 contract ?? ??
- mock smoke test ?? schema validation fixture

?? Answer ?? ??? ? Answer Generation Runner? ??? 28? case? ??? ???? ?? ??.

## 12. ?? ?? ???

1. `answer_eval.draft.jsonl` 28? case? ???? Answer Generation Runner? ????.
2. ?? ???? `query`, `retrieved_contexts`, ?? ??, ?? metadata? ????.
3. `expected_answer_points`, `relevant_chunk_ids`, `label_status`, metric ??? ?? ??? ???? ???.
4. ? case ??? `generated_answer`, `cited_chunk_ids`, `model_name`, `prompt_version`, `generated_at`, `backend`, `top_k`, `run_id`? ????.
5. `retrieved_chunk_ids`? `cited_chunk_ids`? ?? ??? Citation Accuracy? Faithfulness ??? ???? ??.
6. ?? `output/ops_agent/cases`? ?? ?? ??? ??? mock/reference style sample?? ????.
7. report generator ???? Answer Evaluation ?? report integration ?? ???? ??? ????.

## ?? ??

1. ?? Agent Output? ???? ???? NO

?? ???? ??? ? ?? `run_id`, `card_id`, timestamp, retrieved/cited evidence? ?? Agent Output JSON? ???? ???.

2. `v0_ops_handoff_package`? output? ?? ?? ????? NO

`ops_agent_output.example.json`? example??, `ops_agent_output_sample.json`? sample/mock?? ????. report generator? LLM ??? Agent Output Contract ??? ??? report ?????.

3. ?? 28? Answer Evaluation case? ?? ??? ????? NO

`case_id`, `query`, `retrieved_chunk_ids`, `run_id`, `card_id` ?? direct match? ??.

4. ?? ?? ???? ??? ?? ?? ??? ??? ???? ????

?? ?? ???? ???? ???. ?? ?????? ??? ??? ? ??.

- `v0_ops_handoff_package/examples/ops_agent_output.example.json`: v0 output contract ??
- `v0_ops_handoff_package/report_generator_hsj/outputs/ops_agent/ops_agent_output_sample.json`: sample output
- `output/ops_agent/cases/*_with_rag.json`, `output/ops_agent/cases/*_no_rag.json`: mock scenario output
- `docs/contracts/ops_agent_result_v4.example.json`: v4 result contract ??

5. ???? ???? Answer Generation Runner? ?? ???? ???? YES

?? Answer Evaluation?? 28? case?? ? output? ????, ?? ??/??/????/RAG backend/citation ??? ?? ???? ??.
