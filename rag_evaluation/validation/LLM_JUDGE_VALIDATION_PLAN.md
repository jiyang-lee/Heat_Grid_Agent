# LLM Judge Validation Plan

## 목적

2단계에서 LLM Judge를 실행한 뒤 결과가 완전하고 재현 가능한지 검증한다.

## 검증 항목

| 항목 | 검증 방법 |
|---|---|
| 28 case 모두 평가 | `answer_generation_all.jsonl` case_id와 `llm_judge_results.jsonl` case_id 비교 |
| 누락 case 없음 | dataset case_id - judge result case_id가 빈 집합인지 확인 |
| JSON parsing 정상 | JSONL 모든 행을 파싱 |
| Judge 출력 형식 정상 | `llm_judge.schema.json` 필수 필드 및 enum 범위 확인 |
| Summary 재계산 일치 | 평균 점수, hallucination 분포, PASS/REVISE/FAIL count를 case-level 결과에서 재계산 |
| 기존 JSONL 변경 없음 | Answer Generation, Automatic Evaluation, Retrieval 결과 파일 hash 비교 |
| API 사용량 기록 | input/output/total token과 비용 산정 가능 여부 확인 |

## 기존 결과 보존 대상

- `rag_evaluation/results/answer_generation_all.jsonl`
- `rag_evaluation/automatic_evaluation/automatic_answer_eval_results.jsonl`
- `rag_evaluation/results/real_retrieval_results.jsonl`
- `rag_evaluation/results/retrieval_results.jsonl`

## 2단계 산출물

- `rag_evaluation/llm_judge/llm_judge_results.jsonl`
- `rag_evaluation/llm_judge/llm_judge_summary.json`
- `rag_evaluation/validation/LLM_JUDGE_VALIDATION.md`

## 진행 조건

사용자 승인 전에는 API 호출을 수행하지 않는다.
