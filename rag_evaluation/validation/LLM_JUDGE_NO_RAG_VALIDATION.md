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

- Faithfulness 평균: `4.214285714285714`
- Operational Usefulness 평균: `2.7142857142857144`
- Citation Accuracy Semantic 평균: `4.892857142857143`
- Answer Relevance 평균: `3.5`

## 분포

- Hallucination 분포: `{'MINOR': 2, 'NONE': 26}`
- PASS/REVISE/FAIL 분포: `{'PASS': 18, 'REVISE': 10}`
- Judge Confidence 분포: `{'HIGH': 28}`

## Token Usage

- Input Tokens: `70181`
- Output Tokens: `4824`
- Total Tokens: `75005`
- Estimated Cost USD: `None`
- 비용 산정 비고: estimated_total_cost_usd is null because official pricing for the configured model was not confirmed in this evaluation config.

## Retrieval Hit/Miss 비교

- Retrieval Hit: `{'case_count': 0, 'faithfulness_average': None, 'operational_usefulness_average': None, 'citation_accuracy_semantic_average': None, 'answer_relevance_average': None, 'overall_recommendation_distribution': {}, 'hallucination_distribution': {}}`
- Retrieval Miss: `{'case_count': 25, 'faithfulness_average': 4.12, 'operational_usefulness_average': 2.56, 'citation_accuracy_semantic_average': 4.88, 'answer_relevance_average': 3.32, 'overall_recommendation_distribution': {'PASS': 15, 'REVISE': 10}, 'hallucination_distribution': {'MINOR': 2, 'NONE': 23}}`
- answerable=false: `{'case_count': 3, 'faithfulness_average': 5.0, 'operational_usefulness_average': 4.0, 'citation_accuracy_semantic_average': 5.0, 'answer_relevance_average': 5.0, 'overall_recommendation_distribution': {'PASS': 3}, 'hallucination_distribution': {'NONE': 3}}`
- Query Type: `{'keyword_match': {'case_count': 11, 'faithfulness_average': 4.0, 'operational_usefulness_average': 2.5454545454545454, 'citation_accuracy_semantic_average': 4.7272727272727275, 'answer_relevance_average': 3.090909090909091, 'overall_recommendation_distribution': {'PASS': 6, 'REVISE': 5}, 'hallucination_distribution': {'MINOR': 1, 'NONE': 10}}, 'semantic_paraphrase': {'case_count': 7, 'faithfulness_average': 4.0, 'operational_usefulness_average': 2.5714285714285716, 'citation_accuracy_semantic_average': 5.0, 'answer_relevance_average': 3.857142857142857, 'overall_recommendation_distribution': {'PASS': 5, 'REVISE': 2}, 'hallucination_distribution': {'MINOR': 1, 'NONE': 6}}}`

## LLM Judge 결과의 한계

- Judge와 Generation에 동일 모델 계열이 사용되어 자기평가 편향 가능성이 있다.
- 현재 결과는 draft/reference dataset 기반이며 official benchmark가 아니다.
- Recommendation 기준은 `calibration_required` 상태이므로 사람 검수 후 보정이 필요하다.

## 사람 검수 우선 대상

- 우선 대상 case_id: `['retrieval_eval_011', 'retrieval_eval_022', 'retrieval_eval_001', 'retrieval_eval_002', 'retrieval_eval_003', 'retrieval_eval_004', 'retrieval_eval_005', 'retrieval_eval_006', 'retrieval_eval_007', 'retrieval_eval_008', 'retrieval_eval_009', 'retrieval_eval_021']`

## 다음 단계 진행 가능 여부

CONDITIONAL

조건: 사람 검수로 낮은 점수/LOW confidence/REVISE/FAIL case를 우선 확인한 뒤 품질 점수 통합 단계로 진행한다.
