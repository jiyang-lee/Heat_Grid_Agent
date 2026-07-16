# LLM Judge Manual Review

## 검토 목적

LLM Judge 실행 결과를 원본 점수 수정 없이 의미적으로 재검토했다. 검토 기준은 Retrieval evidence, gold relevant label, generated answer, rule-based automatic evaluation, LLM Judge 점수 및 comment의 내부 일관성이다.

## 검토 범위

- 우선 검토 case: `retrieval_eval_006`, `retrieval_eval_008`, `retrieval_eval_016`, `retrieval_eval_002`, `retrieval_eval_003`, `retrieval_eval_005`, `retrieval_eval_007`, `retrieval_eval_011`, `retrieval_eval_013`, `retrieval_eval_014`, `retrieval_eval_015`, `retrieval_eval_019`, `retrieval_eval_024`
- 최고 점수 기준 case: `retrieval_eval_001`, `retrieval_eval_021`
- 원본 결과 파일 수정 여부: 수정하지 않음
- Judge 점수/enum 수정 여부: 수정하지 않음
- 검토 한계: 일부 한국어 원문이 깨져 있어 세부 문장 뉘앙스보다 구조화 필드와 영어 expected_answer_points 중심으로 판단함

## 전체 결론

- Retrieval Miss case에서 낮은 Answer Relevance/Operational Usefulness가 나타나는 것은 대체로 타당하다.
- 다만 Retrieval Miss에서 안전하게 유보한 답변에 `faithfulness=0` 또는 `citation_accuracy_semantic=0`을 주는 case와, 유사한 유보 답변에 `faithfulness=5`, `citation_accuracy_semantic=5`를 주는 case가 섞여 있어 Judge calibration이 필요하다.
- `retrieval_eval_024`는 `hallucination_severity=MAJOR`인데 `overall_recommendation=REVISE`로 남아 있어 final verdict 기준 재확인이 필요하다.
- `retrieval_eval_015`는 cited chunk가 실제 retrieved/gold chunk인데 Judge critique가 citation 문제를 과도하게 지적한 것으로 보인다.
- Generation과 Judge가 모두 `gpt-5.4-mini`라서, 유보 표현과 자체 생성 스타일에 관대한 경향이 일부 보인다. 특히 `HIGH` confidence는 그대로 신뢰하지 말고 evidence 기준 재검토가 필요하다.

## 문제 유형별 Case 목록

| 문제 유형 | case_id |
|---|---|
| RETRIEVAL_FAILURE | `retrieval_eval_002`, `retrieval_eval_003`, `retrieval_eval_005`, `retrieval_eval_007`, `retrieval_eval_011`, `retrieval_eval_014`, `retrieval_eval_019` |
| GENERATION_FAILURE | `retrieval_eval_005`, `retrieval_eval_011`, `retrieval_eval_024` |
| CITATION_FAILURE | `retrieval_eval_002`, `retrieval_eval_015`, `retrieval_eval_024` |
| JUDGE_INCONSISTENCY | `retrieval_eval_006`, `retrieval_eval_008`, `retrieval_eval_013`, `retrieval_eval_015`, `retrieval_eval_016`, `retrieval_eval_024` |
| DATASET_LABEL_ISSUE | 없음. 단, Retrieval Miss case의 answerable=true label은 Retrieval 실패와 분리해서 해석 필요 |
| NO_MATERIAL_ISSUE | `retrieval_eval_001`, `retrieval_eval_021` |
| MULTIPLE | `retrieval_eval_002`, `retrieval_eval_005`, `retrieval_eval_011`, `retrieval_eval_015`, `retrieval_eval_024` |

## Judge 판정 유지 / 재검토

Judge final verdict를 그대로 유지해도 되는 case:

- `retrieval_eval_001`
- `retrieval_eval_002`
- `retrieval_eval_003`
- `retrieval_eval_005`
- `retrieval_eval_007`
- `retrieval_eval_011`
- `retrieval_eval_014`
- `retrieval_eval_019`
- `retrieval_eval_021`

판정 또는 rubric score 재검토가 필요한 case:

- `retrieval_eval_006`: final FAIL은 이해 가능하지만 faithfulness/citation 점수 기준이 Retrieval Miss 유보 정책과 충돌할 수 있음
- `retrieval_eval_008`: `retrieval_eval_006`과 동일한 calibration 이슈
- `retrieval_eval_013`: Retrieval Miss 유보 답변에 citation score 0을 주는 기준이 일관적인지 재검토 필요
- `retrieval_eval_015`: citation score와 critique가 실제 cited chunk와 맞지 않을 가능성
- `retrieval_eval_016`: Operational Usefulness 2인데 PASS인 점은 임시 PASS 기준상 가능하지만 운영 품질 관점에서 재검토 필요
- `retrieval_eval_024`: MAJOR hallucination과 REVISE verdict의 조합 재검토 필요

상위 모델 또는 다른 계열 모델 재평가 최소 case:

- `retrieval_eval_006`
- `retrieval_eval_008`
- `retrieval_eval_013`
- `retrieval_eval_015`
- `retrieval_eval_016`
- `retrieval_eval_024`

## Case별 상세 검토

### retrieval_eval_006

- question: 안전밸브 배출관 유도 위치와 차단밸브 설치 여부
- answerable: `true`
- gold relevant_chunk_ids: `danfoss_substation_operation_extract__p010__c01`, `swedish_f101_operation_extract__p025__c01`
- 실제 retrieval 결과: `danfoss_troubleshooting_table__row001` ~ `row005`; gold chunk 미검색, Retrieval Miss
- generated answer: 현재 검색 근거만으로 안전밸브 배출관/차단밸브 기준을 직접 확인하기 어렵고 추가 문서 또는 현장 확인이 필요하다고 유보
- citation/evidence reference: `cited_chunk_ids=[]`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `0`
- LLM Judge 점수: faithfulness `0`, operational `1`, citation `0`, relevance `1`
- hallucination 판정: `NONE`
- final verdict: `FAIL`
- Judge rationale 또는 critique: 답변이 질문 의도와 gold expected points를 거의 충족하지 못했다고 비판
- Judge confidence: `HIGH`
- 검토 의견: Retrieval 실패로 정답 근거가 없고 답변은 안전하게 유보했다. 최종 FAIL은 “정답 제공 실패” 관점에서는 가능하지만, 근거 없는 주장을 하지 않았으므로 faithfulness 0과 citation 0은 Retrieval Miss 유보 정책과 충돌한다.
- 분류: `RETRIEVAL_FAILURE`, `JUDGE_INCONSISTENCY`

### retrieval_eval_008

- question: 중간점검 신청 시점과 미비 처리
- answerable: `true`
- gold relevant_chunk_ids: `kdhc_inspection_extract__p009__c01`
- 실제 retrieval 결과: Danfoss troubleshooting row001~row005; gold chunk 미검색
- generated answer: 현재 검색 근거만으로 중간점검 신청 시점/미비 처리 방법을 직접 확인하기 어렵다고 유보
- citation/evidence reference: `cited_chunk_ids=[]`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `0`
- LLM Judge 점수: faithfulness `0`, operational `1`, citation `0`, relevance `1`
- hallucination 판정: `NONE`
- final verdict: `FAIL`
- Judge rationale 또는 critique: 기대 답변 핵심인 7일 전 신청, 접수 경로, 재점검 절차를 제공하지 못했다고 비판
- Judge confidence: `HIGH`
- 검토 의견: Retrieval 실패가 원인이고 Generation은 과도한 사실 생성 없이 유보했다. `faithfulness=0`은 “근거 충실도”보다 “정답 미충족”을 벌점화한 것으로 보이며, `hallucination=NONE`과 함께 보면 rubric 축 간 혼선이 있다.
- 분류: `RETRIEVAL_FAILURE`, `JUDGE_INCONSISTENCY`

### retrieval_eval_016

- question: brazed plate heat exchanger와 gasket type 선택 상황 비교
- answerable: `true`
- gold relevant_chunk_ids: `iea_sh_dhw_substation_extract__p070__c01`, `iea_sh_dhw_substation_extract__p071__c01`
- 실제 retrieval 결과: Danfoss operation/troubleshooting chunks; gold chunk 미검색
- generated answer: 검색 근거로는 선택 기준을 명확히 판단하기 어렵고 추가 확인이 필요하다고 유보
- citation/evidence reference: `cited_chunk_ids=[]`
- Automatic Evaluation: coverage `0.3333`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `0`
- LLM Judge 점수: faithfulness `5`, operational `2`, citation `5`, relevance `4`
- hallucination 판정: `NONE`
- final verdict: `PASS`
- Judge rationale 또는 critique: 직접 근거가 없음을 명확히 유보했으므로 faithfulness/citation은 높게 평가, 운영 유용성은 낮게 평가
- Judge confidence: `HIGH`
- 검토 의견: Retrieval Miss 유보 답변에 faithfulness/citation 5를 주는 것은 006/008과 반대 방향이다. 임시 PASS 기준에는 operational usefulness가 포함되지 않아 PASS가 가능하지만, 운영 관점에서는 `operational=2`인 답변을 PASS로 둘지 calibration 필요.
- 분류: `RETRIEVAL_FAILURE`, `JUDGE_INCONSISTENCY`

### retrieval_eval_002

- question: 환수가 낮게 나올 때 순환펌프 쪽 점검 항목
- answerable: `true`
- gold relevant_chunk_ids: `danfoss_troubleshooting_table__row008`
- 실제 retrieval 결과: row001~row005; gold row008 미검색, row004에는 pump power/operation/air 관련 일반 점검 항목 존재
- generated answer: 펌프 전원, 실제 동작, 펌프 하우징 공기 여부를 점검하되 직접 근거 부족으로 추가 확인 필요하다고 답변
- citation/evidence reference: `cited_chunk_ids=[]`; generation warning `retrieval_miss_citations_cleared_by_policy`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `1`
- LLM Judge 점수: faithfulness `3`, operational `3`, citation `2`, relevance `4`
- hallucination 판정: `MINOR`
- final verdict: `REVISE`
- Judge rationale 또는 critique: 핵심 점검 항목은 일부 맞지만 citation이 비어 있고 질문 초점이 분산됐다고 평가
- Judge confidence: `HIGH`
- 검토 의견: Retrieval은 miss지만 row004가 pump 점검을 부분적으로 뒷받침한다. Citation은 strict miss policy 때문에 비워졌으므로 citation 감점은 정책 충돌 성격이 있다. REVISE 판정은 유지 가능하나 원인은 Retrieval Failure와 Citation Policy 이슈로 분리해야 한다.
- 분류: `MULTIPLE` (`RETRIEVAL_FAILURE`, `CITATION_FAILURE`)

### retrieval_eval_003

- question: 급탕 온도 저하/변동 시 욕실 믹서 역류방지밸브가 대상인지
- answerable: `true`
- gold relevant_chunk_ids: `danfoss_troubleshooting_table__row006`
- 실제 retrieval 결과: row001~row005; gold row006 미검색
- generated answer: 현재 근거로는 욕실 믹서 역류방지밸브를 직접 원인으로 확인하기 어렵고 추가 확인이 필요하다고 유보
- citation/evidence reference: `cited_chunk_ids=[]`; generation warning `retrieval_miss_citations_cleared_by_policy`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `1`
- LLM Judge 점수: faithfulness `2`, operational `3`, citation `1`, relevance `4`
- hallucination 판정: `MINOR`
- final verdict: `REVISE`
- Judge rationale 또는 critique: gold expected point를 충분히 반영하지 못했고 citation 연결이 약하다고 평가
- Judge confidence: `MEDIUM`
- 검토 의견: Retrieval Miss가 주원인이다. 답변은 유보 정책을 잘 따랐으나 answerable=true dataset 관점에서는 정답 핵심을 충족하지 못했다. REVISE는 타당하다.
- 분류: `RETRIEVAL_FAILURE`

### retrieval_eval_005

- question: 시운전 전 배관 연결부 필수 확인 순서
- answerable: `true`
- gold relevant_chunk_ids: `danfoss_substation_operation_extract__p010__c01`
- 실제 retrieval 결과: KDH inspection p027/p034 및 troubleshooting row001~row003; gold chunk 미검색
- generated answer: 연결부 상태와 지지 상태 확인을 언급하나, expected sequence인 filling 후 재조임, pressure test 전 점검, heating 후 재확인 흐름은 부족
- citation/evidence reference: `cited_chunk_ids=[]`; generation warning `retrieval_miss_citations_cleared_by_policy`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `1`
- LLM Judge 점수: faithfulness `2`, operational `2`, citation `1`, relevance `3`
- hallucination 판정: `MINOR`
- final verdict: `REVISE`
- Judge rationale 또는 critique: 질문이 요구한 점검 순서를 충분히 제시하지 못했다고 평가
- Judge confidence: `HIGH`
- 검토 의견: Retrieval Miss와 Generation의 부분 답변 문제가 함께 있다. REVISE 유지가 타당하다.
- 분류: `MULTIPLE` (`RETRIEVAL_FAILURE`, `GENERATION_FAILURE`)

### retrieval_eval_007

- question: 국내 준공점검에서 1차측 열량계와 스트레이너 설치 상태 확인
- answerable: `true`
- gold relevant_chunk_ids: `kdhc_inspection_extract__p012__c01`
- 실제 retrieval 결과: `kdhc_inspection_extract__p030__c01` 및 troubleshooting rows; gold chunk 미검색
- generated answer: 직접 설치 상태 기준은 확인하기 어렵고, 1차측 배관 청소/스트레이너 청소 관련 일반 정보만 있다고 유보
- citation/evidence reference: `cited_chunk_ids=[]`; generation warning `retrieval_miss_citations_cleared_by_policy`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `1`
- LLM Judge 점수: faithfulness `3`, operational `3`, citation `2`, relevance `4`
- hallucination 판정: `NONE`
- final verdict: `REVISE`
- Judge rationale 또는 critique: 유보는 안전하지만 직접 답변성이 부족하다고 평가
- Judge confidence: `HIGH`
- 검토 의견: Retrieval 실패가 주원인이다. Citation 빈 배열은 miss policy상 허용되므로 citation 감점은 과도할 수 있지만, 최종 REVISE는 타당하다.
- 분류: `RETRIEVAL_FAILURE`

### retrieval_eval_011

- question: risk score가 높은 지점의 원인 우선순위를 FMEA 기반으로 설명할 근거
- answerable: `true`
- gold relevant_chunk_ids: `fault_priority_extract__p004__c01`, `fault_priority_extract__p005__c01`
- 실제 retrieval 결과: Danfoss troubleshooting row001~row005; gold chunk 미검색
- generated answer: troubleshooting table 기반의 증상/원인/조치 연결을 FMEA 근거처럼 일부 확장해서 설명
- citation/evidence reference: `cited_chunk_ids=[]`; generation warning `retrieval_miss_citations_cleared_by_policy`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `1`
- LLM Judge 점수: faithfulness `3`, operational `3`, citation `2`, relevance `4`
- hallucination 판정: `MINOR`
- final verdict: `REVISE`
- Judge rationale 또는 critique: FMEA 우선순위 기준을 직접 제시하지 못하고 약한 추론이 있다고 평가
- Judge confidence: `HIGH`
- 검토 의견: Retrieval 실패에 더해 Generation이 검색된 troubleshooting table을 FMEA 근거처럼 해석한 부분이 있다. REVISE 유지가 타당하다.
- 분류: `MULTIPLE` (`RETRIEVAL_FAILURE`, `GENERATION_FAILURE`)

### retrieval_eval_013

- question: control valve actuator travel time 설정 오류가 우선순위 연구에서 어떤 위험으로 언급되는지
- answerable: `true`
- gold relevant_chunk_ids: `fault_priority_extract__p009__c01`
- 실제 retrieval 결과: troubleshooting row004~row011; gold chunk 미검색
- generated answer: 직접 확인하기 어렵다고 유보
- citation/evidence reference: `cited_chunk_ids=[]`
- Automatic Evaluation: coverage `0.3333`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `0`
- LLM Judge 점수: faithfulness `1`, operational `2`, citation `0`, relevance `2`
- hallucination 판정: `MINOR`
- final verdict: `REVISE`
- Judge rationale 또는 critique: expected row의 MPN/ranking 정보를 사용하지 못했고 citation이 없다고 평가
- Judge confidence: `HIGH`
- 검토 의견: Retrieval Miss 유보 답변에 citation 0을 주는 것은 014/016의 citation 5와 기준이 다르다. final REVISE는 유지 가능하지만 rubric score 재검토가 필요하다.
- 분류: `RETRIEVAL_FAILURE`, `JUDGE_INCONSISTENCY`

### retrieval_eval_014

- question: 지역난방 기계실 strainer mesh 국제 기준과 압력계 설치 위치
- answerable: `true`
- gold relevant_chunk_ids: `iea_sh_dhw_substation_extract__p074__c01`, `swedish_f101_operation_extract__p023__c01`
- 실제 retrieval 결과: troubleshooting rows 및 Danfoss operation chunks; gold chunk 미검색
- generated answer: 기준값과 압력계 목적을 확인하기 어렵다고 유보
- citation/evidence reference: `cited_chunk_ids=[]`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `0`
- LLM Judge 점수: faithfulness `5`, operational `2`, citation `5`, relevance `2`
- hallucination 판정: `NONE`
- final verdict: `REVISE`
- Judge rationale 또는 critique: 허위 정보는 없지만 기대 답변 핵심을 제공하지 못했다고 평가
- Judge confidence: `HIGH`
- 검토 의견: Retrieval Miss 유보 답변으로 faithfulness/citation 고점은 정책과 일치한다. 낮은 relevance/operational 때문에 REVISE인 것도 타당하다.
- 분류: `RETRIEVAL_FAILURE`

### retrieval_eval_015

- question: two-port control valve 사용 이유와 self-acting/electric control valve 선택 근거
- answerable: `true`
- gold relevant_chunk_ids: `iea_sh_dhw_substation_extract__p073__c01`
- 실제 retrieval 결과: gold chunk가 rank 4에 포함됨
- generated answer: two-port 경제성, self-acting/electric control 가능성, 추가 선택 기준 확인 필요성을 답변
- citation/evidence reference: `cited_chunk_ids=["iea_sh_dhw_substation_extract__p073__c01"]`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, warning `0`
- LLM Judge 점수: faithfulness `4`, operational `4`, citation `3`, relevance `5`
- hallucination 판정: `MINOR`
- final verdict: `REVISE`
- Judge rationale 또는 critique: cited chunk가 직접 근거를 가리키지 않는다는 식의 critique가 있으나 실제 cited chunk는 gold/retrieved chunk와 일치함
- Judge confidence: `HIGH`
- 검토 의견: Citation Accuracy 3은 과도하게 낮을 수 있다. 답변이 selection 기준 일부를 덜 반영했을 가능성은 있으나 citation ID 자체는 적절하다. 다른 모델로 재평가 권장.
- 분류: `MULTIPLE` (`JUDGE_INCONSISTENCY`, `CITATION_FAILURE`)

### retrieval_eval_019

- question: 준공점검 서식에서 난방순환펌프와 판형열교환기에 무엇을 확인/기록하는지
- answerable: `true`
- gold relevant_chunk_ids: `kdhc_inspection_extract__p046__c01`
- 실제 retrieval 결과: troubleshooting row001~row005; gold chunk 미검색
- generated answer: 검색 근거로는 서식의 기록 항목을 직접 확인하기 어렵다고 유보
- citation/evidence reference: `cited_chunk_ids=[]`; generation warning `retrieval_miss_citations_cleared_by_policy`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `1`
- LLM Judge 점수: faithfulness `1`, operational `2`, citation `1`, relevance `2`
- hallucination 판정: `MINOR`
- final verdict: `REVISE`
- Judge rationale 또는 critique: expected recording fields를 반영하지 못했다고 평가
- Judge confidence: `HIGH`
- 검토 의견: Retrieval 실패가 결정적이다. 정답 제공 실패 관점의 REVISE는 타당하지만, 유보 답변 자체의 faithfulness/citation 감점은 calibration 필요성이 있다.
- 분류: `RETRIEVAL_FAILURE`

### retrieval_eval_024

- question: commissioning 시 난방/DHW balance에 필요한 기록과 기능평가
- answerable: `true`
- gold relevant_chunk_ids: `swedish_f101_operation_extract__p028__c01`
- 실제 retrieval 결과: Danfoss operation chunks; gold chunk 미검색
- generated answer: flushing, pressure, strainer cleaning, connection tightening, safety valve testing 등 일부 commissioning 관련 내용을 답변하나 expected balancing/recording/temperature-measurement 확인과 어긋남
- citation/evidence reference: `cited_chunk_ids=[]`; generation warning `retrieval_miss_citations_cleared_by_policy`
- Automatic Evaluation: coverage `0.0`, citation_valid `true`, retrieval_miss_policy_passed `true`, warning `1`
- LLM Judge 점수: faithfulness `2`, operational `2`, citation `1`, relevance `3`
- hallucination 판정: `MAJOR`
- final verdict: `REVISE`
- Judge rationale 또는 critique: unsupported commissioning record details and pressure guidance, expected balancing/recording omission, citation absence를 지적
- Judge confidence: `HIGH`
- 검토 의견: Retrieval 실패와 Generation의 부분 오답/과잉 적용이 함께 있다. `MAJOR` hallucination인데 final verdict가 `REVISE`인 점은 임시 기준상 “운영상 위험한 MAJOR” 여부를 명시하지 않아 애매하지만, 보수적으로 FAIL 재검토가 필요하다.
- 분류: `MULTIPLE` (`RETRIEVAL_FAILURE`, `GENERATION_FAILURE`, `CITATION_FAILURE`, `JUDGE_INCONSISTENCY`)

### retrieval_eval_001

- question: 난방 불량 시 strainer/filter clog 또는 differential pressure controller 이상을 원인 후보로 볼 수 있는지
- answerable: `true`
- gold relevant_chunk_ids: `danfoss_troubleshooting_table__row001`
- 실제 retrieval 결과: gold chunk가 rank 1에 포함됨
- generated answer: clogged dirt strainer/filter와 differential pressure controller 이상을 가능한 원인 후보로 제시하고 확정 진단은 피함
- citation/evidence reference: `cited_chunk_ids=["danfoss_troubleshooting_table__row001"]`
- Automatic Evaluation: coverage `0.3333`, citation_valid `true`, warning `0`
- LLM Judge 점수: faithfulness `5`, operational `5`, citation `5`, relevance `5`
- hallucination 판정: `NONE`
- final verdict: `PASS`
- Judge rationale 또는 critique: 근거와 직접 일치하고 forbidden claim을 피했다고 평가
- Judge confidence: `HIGH`
- 검토 의견: evidence, citation, verdict가 일관적이다. Automatic coverage가 낮은 것은 rule-based token matching 한계로 보이며 의미 평가와 충돌하지 않는다.
- 분류: `NO_MATERIAL_ISSUE`

### retrieval_eval_021

- question: 난방 불량에서 pump power, actuator, thermostat까지 함께 볼 troubleshooting row가 있는지
- answerable: `true`
- gold relevant_chunk_ids: `danfoss_troubleshooting_table__row004`
- 실제 retrieval 결과: gold chunk가 rank 1에 포함됨
- generated answer: row004의 thermostat, actuator, controller, power outage, pump, air pocket 관련 원인과 점검 방향을 요약하고 현재 현장 원인 확정은 피함
- citation/evidence reference: `cited_chunk_ids=["danfoss_troubleshooting_table__row004"]`
- Automatic Evaluation: coverage `0.3333`, citation_valid `true`, warning `0`
- LLM Judge 점수: faithfulness `5`, operational `5`, citation `5`, relevance `5`
- hallucination 판정: `NONE`
- final verdict: `PASS`
- Judge rationale 또는 critique: 유사 troubleshooting row로서 근거 범위 내 요약이라고 평가
- Judge confidence: `HIGH`
- 검토 의견: evidence, citation, verdict가 일관적이다. 최고 점수 기준 사례로 유지 가능하다.
- 분류: `NO_MATERIAL_ISSUE`

## Judge 내부 일관성 검토

- 점수와 final verdict 일치: 대부분 일치하나 `retrieval_eval_016`은 operational `2`에도 PASS이며, 이는 현재 임시 PASS 기준에 operational usefulness가 들어가지 않기 때문에 발생한다. 운영 품질 기준으로는 재검토 필요.
- Faithfulness와 hallucination 일치: `retrieval_eval_006`, `retrieval_eval_008`은 faithfulness `0`이지만 hallucination `NONE`이다. 이는 “거짓 주장”이 아니라 “정답 미제공”을 faithfulness에 반영한 것으로 보이며 rubric 축 혼선 가능성이 있다.
- Rationale과 점수 일치: `retrieval_eval_015`는 critique가 cited chunk 적절성에 의문을 제기하지만 실제 cited chunk가 gold/retrieved chunk이므로 citation score `3`은 재검토 필요.
- Citation 문제 과대 반영: Retrieval Miss에서 empty citation을 허용하는 정책이 있는데도 `retrieval_eval_006`, `retrieval_eval_008`, `retrieval_eval_013`, `retrieval_eval_019`는 citation low score를 받았다. 이 기준은 `retrieval_eval_014`, `retrieval_eval_016`의 citation high score와 맞지 않는다.

## 근거 기반 타당성 검토

- Retrieval Hit case인 `retrieval_eval_001`, `retrieval_eval_021`은 generated answer의 핵심 주장이 cited chunk로 직접 뒷받침된다.
- `retrieval_eval_015`도 Retrieval Hit이며 citation ID는 gold chunk와 일치한다. 다만 답변이 selection 기준 일부를 덜 반영했는지는 사람 검수 필요.
- Retrieval Miss case 대부분은 정답 chunk가 검색되지 않아 expected_answer_points를 충족하기 어렵다.
- `retrieval_eval_024`는 검색된 partial evidence를 commissioning 요구사항 전체 답변처럼 사용한 위험이 가장 크다.
- answerable=true이지만 Retrieval Miss인 case는 Answer Generation 품질만으로 벌점화하지 말고 Retrieval Failure로 분리해야 한다.

## 동일 모델 편향 검토

- Generation과 Judge 모두 `gpt-5.4-mini`이다.
- `retrieval_eval_014`, `retrieval_eval_016`처럼 안전한 유보 답변에 faithfulness/citation을 매우 높게 주는 경향은, 같은 모델이 자신의 유보 전략을 우호적으로 평가했을 가능성이 있다.
- 반대로 `retrieval_eval_006`, `retrieval_eval_008`처럼 유보 답변을 faithfulness/citation 0으로 평가한 case도 있어 모델 편향이라기보다 rubric calibration 불안정성이 더 커 보인다.
- `HIGH` confidence가 15개 대상 중 대부분에 부여되었지만, evidence 기준으로 보면 confidence를 그대로 신뢰하기 어렵다.

## 실행 코드 변경 확인

검토 대상:

- `rag_evaluation/scripts/run_llm_judge.py`
- `rag_evaluation/scripts/llm_judge_utils.py`

확인 결과:

- Prompt 또는 Rubric 변경 여부: 변경 없음. `rag_evaluation/llm_judge/llm_judge_prompt.md`, `LLM_JUDGE_GUIDE.md`, schema는 이번 실행 승인 후 수정하지 않았음.
- 결과 점수나 enum 임의 보정 로직 여부: 없음. 모델이 반환한 rubric 점수와 enum을 그대로 `normalize_judge_record()`에 복사하고, 별도 점수 보정은 하지 않음.
- 누락 필드 자동 생성 로직 여부: `judge_model`, `judge_prompt_version`, `evaluation_time`, `usage`, `estimated_cost_usd=null` 같은 실행 메타데이터는 자동 생성함. 그러나 `faithfulness`, `hallucination_severity`, `overall_recommendation` 등 Judge rubric 필드는 누락 시 보정하지 않고 validation error로 남기는 구조임.
- 파싱 오류를 숨기는 fallback 여부: 없음. JSON code fence 제거 후 parse하며, 실패 시 retry 후 실패 case로 기록한다. 점수 fallback이나 기본 PASS/FAIL 생성은 없음.
- 재실행 및 덮어쓰기 보호 관련 변경 여부: 있음. `llm_judge_results.jsonl` 또는 `llm_judge_summary.json`이 존재하면 `--overwrite` 없이는 중단한다.
- 각 변경 시점: 모든 실행 코드 변경은 API 호출 전에 승인 후 추가되었고, API 실행 중 또는 실행 후 결과 점수 보정을 위한 코드 변경은 없었음.

## 다음 단계 진행 가능 여부

CONDITIONAL

조건:

- `retrieval_eval_006`, `retrieval_eval_008`, `retrieval_eval_013`, `retrieval_eval_015`, `retrieval_eval_016`, `retrieval_eval_024`를 다른 계열 또는 상위 모델로 최소 재평가한다.
- Retrieval Miss 유보 답변의 faithfulness/citation scoring 기준을 calibration한다.
- `MAJOR` hallucination과 final verdict의 관계를 명확히 한다.
- 품질 통합 점수 산출 전, Retrieval Failure와 Generation Failure를 분리하는 reporting rule을 고정한다.
