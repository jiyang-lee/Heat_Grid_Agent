# LLM Judge Validation

## 실행 목적

Answer Generation 28건에 대해 LLM Judge 기반 의미 평가를 수행하고, 결과 JSONL과 summary의 구조 및 집계를 검증한다.

## 실행 설정

- Judge Model: `gpt-5.4-mini`
- Judge Prompt Version: `llm-judge-v1.0-draft`
- Temperature: `0`
- Generation Models: `gpt-5.4-mini`
- Judge와 Generation 동일 모델 여부: `True`
- Recommendation Criteria Status: `calibration_required`

## 처리 결과

- 평가 대상 case 수: `28`
- 성공 case 수: `28`
- 실패 case 수: `0`
- 실패 case_id: `[]`
- 실제 API 호출 수: `28`
- 재시도 횟수: `0`

## 검증 결과

- JSONL 행 수: `28`
- 중복 case_id: `[]`
- 누락 case_id: `[]`
- Schema 검증 오류 수: `0`
- 입력 파일 해시 유지: `True`

## 주요 평균

- Faithfulness 평균: `3.607142857142857`
- Operational Usefulness 평균: `3.2857142857142856`
- Citation Accuracy Semantic 평균: `3.2857142857142856`
- Answer Relevance 평균: `4.035714285714286`

## 분포

- Hallucination 분포: `{'MAJOR': 1, 'MINOR': 11, 'NONE': 16}`
- PASS/REVISE/FAIL 분포: `{'FAIL': 2, 'PASS': 16, 'REVISE': 10}`
- Judge Confidence 분포: `{'HIGH': 27, 'MEDIUM': 1}`

## Token Usage

- Input Tokens: `119258`
- Output Tokens: `6039`
- Total Tokens: `125297`
- Estimated Cost USD: `None`
- 비용 산정 비고: estimated_total_cost_usd is null because official pricing for the configured model was not confirmed in this evaluation config.

## Retrieval Hit/Miss 비교

- Retrieval Hit: `{'case_count': 10, 'faithfulness_average': 4.5, 'operational_usefulness_average': 4.3, 'citation_accuracy_semantic_average': 4.3, 'answer_relevance_average': 5.0, 'overall_recommendation_distribution': {'PASS': 9, 'REVISE': 1}, 'hallucination_distribution': {'MINOR': 5, 'NONE': 5}}`
- Retrieval Miss: `{'case_count': 15, 'faithfulness_average': 2.7333333333333334, 'operational_usefulness_average': 2.466666666666667, 'citation_accuracy_semantic_average': 2.2666666666666666, 'answer_relevance_average': 3.2, 'overall_recommendation_distribution': {'FAIL': 2, 'PASS': 4, 'REVISE': 9}, 'hallucination_distribution': {'MAJOR': 1, 'MINOR': 6, 'NONE': 8}}`
- answerable=false: `{'case_count': 3, 'faithfulness_average': 5.0, 'operational_usefulness_average': 4.0, 'citation_accuracy_semantic_average': 5.0, 'answer_relevance_average': 5.0, 'overall_recommendation_distribution': {'PASS': 3}, 'hallucination_distribution': {'NONE': 3}}`
- Query Type: `{'keyword_match': {'case_count': 11, 'faithfulness_average': 3.5454545454545454, 'operational_usefulness_average': 3.3636363636363638, 'citation_accuracy_semantic_average': 3.272727272727273, 'answer_relevance_average': 4.090909090909091, 'overall_recommendation_distribution': {'FAIL': 1, 'PASS': 7, 'REVISE': 3}, 'hallucination_distribution': {'MINOR': 5, 'NONE': 6}}, 'semantic_paraphrase': {'case_count': 7, 'faithfulness_average': 3.142857142857143, 'operational_usefulness_average': 2.857142857142857, 'citation_accuracy_semantic_average': 2.4285714285714284, 'answer_relevance_average': 4.0, 'overall_recommendation_distribution': {'PASS': 2, 'REVISE': 5}, 'hallucination_distribution': {'MAJOR': 1, 'MINOR': 5, 'NONE': 1}}}`

## LLM Judge 결과의 한계

- Judge와 Generation에 동일 모델 계열이 사용되어 자기평가 편향 가능성이 있다.
- 현재 결과는 draft/reference dataset 기반이며 official benchmark가 아니다.
- Recommendation 기준은 `calibration_required` 상태이므로 사람 검수 후 보정이 필요하다.

## 사람 검수 우선 대상

- 우선 대상 case_id: `['retrieval_eval_006', 'retrieval_eval_008', 'retrieval_eval_016', 'retrieval_eval_002', 'retrieval_eval_003', 'retrieval_eval_005', 'retrieval_eval_007', 'retrieval_eval_011', 'retrieval_eval_013', 'retrieval_eval_014', 'retrieval_eval_015', 'retrieval_eval_019', 'retrieval_eval_024']`

## 다음 단계 진행 가능 여부

CONDITIONAL

조건: 사람 검수로 낮은 점수/LOW confidence/REVISE/FAIL case를 우선 확인한 뒤 품질 점수 통합 단계로 진행한다.
