# Answer Generation Readiness

## 1. 목적

`AGENT_OUTPUT_AUDIT.md` 결과에 따라 기존 Agent Output은 실제 실행 결과로 재사용하지 않는다. 이 문서는 `answer_eval.draft.jsonl` 28개 case에 대해 새 답변을 생성하기 위한 Runner 준비 상태와 Pilot 5건 실행 결과를 기록한다.

## 2. 기준 문서와 정책

- 정책 문서: `rag_evaluation/EVALUATION_POLICY.md`
- 입력 데이터셋: `rag_evaluation/answer_evaluation/answer_eval.draft.jsonl`
- Prompt: `rag_evaluation/answer_generation/answer_generation_prompt.md`
- Runner: `rag_evaluation/scripts/run_answer_generation.py`
- Utility: `rag_evaluation/scripts/answer_generation_utils.py`
- Pilot 결과: `rag_evaluation/results/answer_generation_pilot.jsonl`

현재 전제:

- `dataset_status=draft`
- `result_level=reference`
- `official_benchmark=false`
- `retrieval_backend=jsonl`
- `top_k=5`

## 3. API 호출 가능 여부

API 호출 가능 여부: YES, 네트워크 권한 승인 후 Pilot 5건 호출 성공.

확인 내용:

- 프로세스 환경 변수에는 `OPENAI_API_KEY`가 없었다.
- `.env`에는 `OPENAI_API_KEY`가 설정되어 있었다.
- API Key 값은 출력하지 않았다.
- 최초 일반 샌드박스 실행은 Windows 소켓 접근 제한으로 실패했다.
- 네트워크 권한 승인 후 동일 Pilot 5건 재실행에 성공했다.

## 4. 사용할 모델 설정

| 항목 | 값 |
|---|---|
| model_name | `gpt-5.4-mini` |
| prompt_version | `answer-generation-v1.0-draft` |
| temperature | `0` |
| timeout_seconds | `60` |
| max_retries | `2` |

모델명은 `HEATGRID_OPENAI_MODEL`, `OPENAI_MODEL`, config 기본값 순서로 해석한다.

## 5. Prompt 정답 Label 누수 검증

생성 입력에 포함하는 필드:

- `case_id`
- `query`
- `category`
- `query_intent`
- `query_type`
- `difficulty`
- `answerable`
- `retrieval_hit_at_5`
- `retrieved_contexts`
- 운영 안전 규칙

생성 입력에서 제외하는 필드:

- `expected_answer_points`
- `relevant_chunk_ids`
- `partially_relevant_chunk_ids`
- `forbidden_claims`
- `human_scores`
- `automated_scores`
- `label_status`
- `metrics`
- `evaluation_metadata`
- 평가 결과

dry-run 결과:

- selected_count: 5
- warning_count: 0
- 정답 label 입력 누수: 없음

## 6. retrieved_contexts 연결 상태

`answer_eval.draft.jsonl`의 각 case는 `retrieved_chunk_ids`와 `retrieved_contexts`를 함께 포함한다. Runner는 `retrieved_contexts`에서 다음 필드만 생성 입력으로 전달한다.

- `rank`
- `chunk_id`
- `document_title`
- `section_title`
- `rag_role`
- `score`
- `text`

`expected_answer_points`, `relevant_chunk_ids`, `partially_relevant_chunk_ids`는 전달하지 않는다.

## 7. cited_chunk_ids 검증 가능 여부

검증 가능 여부: YES.

Runner는 모델 출력의 `cited_chunk_ids`를 case별 retrieved `chunk_id` 집합과 비교한다.

검증 규칙:

- retrieved chunk에 없는 citation은 warning 처리한다.
- `document_id`, 문서 제목, PDF 파일명, page, section을 citation으로 쓰는 경우 warning 처리한다.
- `generated_answer`와 `cited_chunk_ids`를 분리 저장한다.
- JSON 파싱 실패, empty answer, citation 형식 오류를 case별 `warnings` 또는 `error`에 기록한다.

Pilot 검증 결과:

- Pilot rows: 5
- JSONL 파싱 가능: 5/5
- generated_answer 비어 있음: 0
- citation warning: 0
- retrieved chunk 외 citation: 0
- 평가 label 문자열 노출: 0
- error: 0

## 8. Pilot 5건 선정 결과

| 순서 | 선정 조건 | case_id | query_type | answerable | retrieval_hit_at_5 | 선정 이유 |
|---:|---|---|---|---|---|---|
| 1 | Retrieval Hit + keyword_match | `retrieval_eval_001` | `keyword_match` | true | true | Hit 조건에서 keyword 기반 답변 생성 검증 |
| 2 | Retrieval Hit + semantic_paraphrase | `retrieval_eval_015` | `semantic_paraphrase` | true | true | Hit 조건에서 의미변환 질문 처리 검증 |
| 3 | Retrieval Miss + keyword_match | `retrieval_eval_002` | `keyword_match` | true | false | Miss 조건에서 근거 부족 표현 검증 |
| 4 | Retrieval Miss + semantic_paraphrase | `retrieval_eval_003` | `semantic_paraphrase` | true | false | Miss 조건에서 사전지식 단정 억제 검증 |
| 5 | answerable=false | `retrieval_eval_026` | `negative_or_unanswerable` | false | false | 답변 불가 질문에서 유보 표현 검증 |

## 9. 예상 API 호출 횟수

- `--dry-run`: 0회
- `--pilot`: 5회
- `--case-id`: 1회
- `--all`: 28회

이번 단계에서 `--all`은 자동 실행하지 않았다.

## 10. 실행 결과

실행 명령:

```powershell
python rag_evaluation/scripts/run_answer_generation.py --dry-run
python rag_evaluation/scripts/run_answer_generation.py --pilot
```

dry-run 결과:

- selected_count: 5
- warning_count: 0
- message_count: 각 case 2
- input_context_count: 각 case 5

Pilot 결과:

- generated_count: 5
- failure_count: 0
- citation_warning_count: 0
- output_path: `rag_evaluation/results/answer_generation_pilot.jsonl`

주의:

- 최초 Pilot 시도는 샌드박스 네트워크 제한으로 실패 record를 생성했다.
- 네트워크 권한 승인 후 재실행했고, 최종 `answer_generation_pilot.jsonl`은 성공 결과 5건으로 덮어썼다.

## 11. 재실행 및 실패 복구 방법

특정 case만 재실행:

```powershell
python rag_evaluation/scripts/run_answer_generation.py --case-id retrieval_eval_001
```

Pilot 전체 재실행:

```powershell
python rag_evaluation/scripts/run_answer_generation.py --pilot
```

결과를 누적 저장하려면 `--append`를 함께 사용한다.

```powershell
python rag_evaluation/scripts/run_answer_generation.py --case-id retrieval_eval_001 --append
```

실패 case는 `error` 필드가 null이 아닌 row로 식별한다.

## 12. 전체 28건 실행 전 확인할 사항

1. Pilot 5건의 사람 검수 또는 최소 AI 검토 의견을 먼저 확인한다.
2. Retrieval Miss case에서 답변이 과도하게 확정적이지 않은지 검수한다.
3. answerable=false case에서 유보 표현이 충분한지 검수한다.
4. citation이 의미적으로도 핵심 주장을 뒷받침하는지 확인한다.
5. 모델명과 Prompt version을 고정한다.
6. 네트워크 권한과 API 사용량을 확인한다.
7. `--all` 실행 전 기존 `answer_generation_pilot.jsonl`을 별도 보존할지 결정한다.
8. 전체 결과 파일명을 pilot과 분리할지 결정한다.

## 13. 최종 판단

Answer Generation Runner 구현 상태: READY.

Pilot 5건 실행 상태: SUCCESS.

전체 28건 실행 가능 여부: 기술적으로 가능하지만, Pilot 결과 검수 후 실행 권장.
