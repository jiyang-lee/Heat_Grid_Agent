# Real Retrieval Result Check

## 1. ?? ??

- Report: `rag_evaluation/reports/REAL_RETRIEVAL_REFERENCE_REPORT.md`
- Case results: `rag_evaluation/results/real_retrieval_results.jsonl`
- Raw outputs: `rag_evaluation/results/raw_retrieval_outputs.jsonl`
- Summary: `rag_evaluation/results/real_retrieval_summary.json`
- Corpus: `data/rag_sources/metadata/rag_chunks.jsonl`

## 2. actual_backend ??

- ?? ?? row: 28
- actual_backend ??: {'jsonl': 28}
- ??: 28? ?? `jsonl`??.

## 3. retrieved_chunk_ids Corpus ??

- corpus chunk ?: 90
- ?? ??? ??? chunk ID ? corpus? ?? ID ?: 0
- ??: ??? ??? `retrieved_chunk_ids`? ?? ?? corpus chunk ID?.

## 4. Recall@5=0 Case

- case ?: 15
- case ??: `retrieval_eval_002`, `retrieval_eval_003`, `retrieval_eval_005`, `retrieval_eval_006`, `retrieval_eval_007`, `retrieval_eval_008`, `retrieval_eval_010`, `retrieval_eval_011`, `retrieval_eval_012`, `retrieval_eval_013`, `retrieval_eval_014`, `retrieval_eval_016`, `retrieval_eval_017`, `retrieval_eval_019`, `retrieval_eval_024`
- category ??: `fault_cause`=1, `inspection_action`=5, `operating_standard`=5, `priority_reason`=3, `safety_caution`=1
- query_type ??: `keyword_match`=6, `multi_condition`=4, `semantic_paraphrase`=5
- query_intent ??: `comparison`=1, `fault_cause`=1, `inspection_action`=5, `operating_standard`=4, `priority_reason`=3, `safety`=1
- difficulty ??: `easy`=4, `hard`=3, `medium`=8

??: Recall@5=0 case? `inspection_action`, `operating_standard`, `priority_reason`? ?? ????. ??? query? ?? chunk? ?? semantic/operating-standard ???? lexical fallback? ??? ????.

## 5. Recall@5>0 Case

- case ?: 10
- case ??: `retrieval_eval_001`, `retrieval_eval_004`, `retrieval_eval_009`, `retrieval_eval_015`, `retrieval_eval_018`, `retrieval_eval_020`, `retrieval_eval_021`, `retrieval_eval_022`, `retrieval_eval_023`, `retrieval_eval_025`
- category ??: `fault_cause`=1, `inspection_action`=2, `operating_standard`=3, `safety_caution`=2, `similar_case`=2
- query_type ??: `keyword_match`=5, `multi_condition`=3, `semantic_paraphrase`=2
- query_intent ??: `comparison`=1, `fault_cause`=3, `inspection_action`=2, `operating_standard`=2, `safety`=2
- relevant label ? ??: `1`=10

?? ??:

- Recall@5>0 case? ?? relevant label? 1?? case??.
- keyword ?? ??? ??/?? ???? query? ??? ??? ????? ???.
- Danfoss troubleshooting row, ?? ??? keyword, connection principle?? chunk text? query token? ?? case?? hit? ????.

## 6. answerable=false 3? ?? ??

| case_id | retrieved count | Top-5 chunk IDs |
|---|---:|---|
| `retrieval_eval_026` | 5 | `kdhc_inspection_extract__p022__c01`, `kdhc_inspection_extract__p027__c01`, `danfoss_substation_operation_extract__p005__c01`, `danfoss_substation_operation_extract__p014__c01`, `danfoss_substation_operation_extract__p020__c01` |
| `retrieval_eval_027` | 5 | `kdhc_inspection_extract__p044__c01`, `danfoss_troubleshooting_table__row001`, `danfoss_troubleshooting_table__row002`, `danfoss_troubleshooting_table__row003`, `danfoss_troubleshooting_table__row004` |
| `retrieval_eval_028` | 5 | `kdhc_inspection_extract__p046__c01`, `kdhc_inspection_extract__p008__c01`, `kdhc_inspection_extract__p032__c01`, `kdhc_inspection_extract__p045__c01`, `danfoss_troubleshooting_table__row001` |

??: unanswerable case? JSONL ??? top-5? ????. ?? metric ????? ?????, no-answer retrieval ?? over-retrieval ???? ?? ??? ? ??.

## 7. keyword_match vs semantic_paraphrase ?? ??

| query_type | n | Recall@5 | HitRate@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|---:|
| `keyword_match` | 11 | 0.4545 | 0.4545 | 0.3939 | 0.3148 |
| `multi_condition` | 7 | 0.4286 | 0.4286 | 0.3571 | 0.2510 |
| `semantic_paraphrase` | 7 | 0.2857 | 0.2857 | 0.1786 | 0.2919 |

?? ??:

- `keyword_match`: Recall@5=0.4545, HitRate@5=0.4545
- `semantic_paraphrase`: Recall@5=0.2857, HitRate@5=0.2857

??: keyword_match? semantic_paraphrase?? Recall@5? HitRate@5? ??. ?? JSONL lexical fallback ????? ?? ?? ??? ???? ?? ???? ?? ??? ? ????.

## 8. Summary ??? ??

- case-level ???? ???? macro metrics? summary? `macro_average_metrics` ?? ??: `True`
- case_count ??: results=28, raw=28, summary=28
- evaluated_case_count: ???=25, summary=25

??? metric:

| metric | recalculated | summary |
|---|---:|---:|
| `hit_rate_at_1` | 0.2800 | 0.2800 |
| `hit_rate_at_3` | 0.3600 | 0.3600 |
| `hit_rate_at_5` | 0.4000 | 0.4000 |
| `mrr` | 0.3233 | 0.3233 |
| `ndcg_at_5` | 0.2905 | 0.2905 |
| `precision_at_1` | 0.2800 | 0.2800 |
| `precision_at_3` | 0.1200 | 0.1200 |
| `precision_at_5` | 0.0800 | 0.0800 |
| `recall_at_1` | 0.2800 | 0.2800 |
| `recall_at_3` | 0.3600 | 0.3600 |
| `recall_at_5` | 0.4000 | 0.4000 |

## 9. ?? ??

?? ??. ?? ?? ??? ???? ???, ? ?? ??? ????.

??: ? ??? `label_status=draft`, `review_required=true`? review dataset ?? Draft/Reference ???? Official Benchmark? ???.
