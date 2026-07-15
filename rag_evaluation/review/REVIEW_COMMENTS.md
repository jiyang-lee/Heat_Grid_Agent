# Retrieval 평가 데이터셋 AI 검토 의견

이 문서는 AI의 검토 의견이다. `relevant_chunk_ids`, `partially_relevant_chunk_ids`, `irrelevant_but_confusable_chunk_ids`, `label_status`, `review_required`, `answerable`은 변경하지 않았다. 아래 의견은 사람이 최종 검수할 때 참고하기 위한 권장/확인 필요/도메인 전문가 검토 권장 메모다.

## 우선 검토 대상 요약

- 1순위: `retrieval_eval_012`, `retrieval_eval_014`, `retrieval_eval_028`
- 그다음: hard 난이도, unanswerable, relevant chunk가 여러 개인 case
- 도메인 전문가 검토 권장 case: `retrieval_eval_006`, `retrieval_eval_010`, `retrieval_eval_012`, `retrieval_eval_014`, `retrieval_eval_018`, `retrieval_eval_020`, `retrieval_eval_028`

## Case별 검토 의견

### retrieval_eval_012

- 현재 Relevant Chunk가 질문에 직접 답하는지: 확인 필요.
- Partially Relevant가 더 적절한지: 일부 relevant 후보는 partially relevant에 가까울 수 있다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 우선순위 평가 축 자체는 일치하지만, strainer-specific priority 근거가 충분한지는 확인 필요.
- 추가 확인이 필요한 사항: `fault_priority_extract__p006__c01`, `fault_priority_extract__p008__c01`가 strainer fault priority를 직접 설명하는지 원문 표/그림 기준 확인이 필요하다.
- 검토 의견: 도메인 전문가 검토 권장. 질문은 strainer fault priority를 묻지만 현재 relevant 후보는 fault grouping과 MPN dimension 설명에 더 가까워 보인다. strainer 행이 명확히 추출되어 있지 않다면 partial로 낮추거나 다른 chunk 추가가 필요할 수 있다.
- 검토 신뢰도: 중간.

### retrieval_eval_014

- 현재 Relevant Chunk가 질문에 직접 답하는지: 대체로 직접 답한다.
- Partially Relevant가 더 적절한지: `iea_sh_dhw_substation_extract__p074__c01`는 relevant로 적절해 보이고, Swedish F:101 chunk는 비교 기준으로 relevant 또는 partial 여부를 검수해야 한다.
- Expected Answer Points가 Chunk 원문과 일치하는지: IEA의 1.0~1.6 mm 및 pressure gauge 설명은 일치한다. Swedish 0.6 mm 기준은 적용 맥락 혼동 위험이 있다.
- 추가 확인이 필요한 사항: IEA 기준과 Swedish F:101 기준을 하나의 보편 기준처럼 합치지 않도록 검수해야 한다.
- 검토 의견: 도메인 전문가 검토 권장. 다중 문서 비교 case로 유용하지만, 국제 기준 간 수치 차이를 source context별로 분리해야 한다.
- 검토 신뢰도: 높음.

### retrieval_eval_028

- 현재 Relevant Chunk가 질문에 직접 답하는지: `relevant_chunk_ids`가 비어 있어야 하는 unanswerable case로 적절해 보인다.
- Partially Relevant가 더 적절한지: 현재 partial 후보는 설계 변수 설명에는 도움이 되지만 미래 날씨 기반 kW 계산에는 직접 답하지 않는다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 정적 corpus로 미래 날씨와 설계 계산을 수행할 수 없다는 취지는 적절하다.
- 추가 확인이 필요한 사항: 평가에서 unanswerable case를 Retrieval 지표에서 제외할지, no-answer 평가로 별도 집계할지 결정해야 한다.
- 검토 의견: 도메인 전문가 검토 권장. 답변 불가 판정은 맞아 보이나, 설계 계산 domain에서는 어떤 입력이 있으면 answerable로 바뀌는지 기준을 명확히 해야 한다.
- 검토 신뢰도: 높음.

### retrieval_eval_006

- 현재 Relevant Chunk가 질문에 직접 답하는지: 대체로 직접 답한다.
- Partially Relevant가 더 적절한지: Danfoss와 Swedish F:101 두 chunk 모두 안전밸브 배출/차단밸브 조건에 직접 관련되어 relevant 후보로 타당해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 배출관을 drain/floor drain으로 유도하고 차단밸브 금지를 말하는 내용은 일치한다.
- 추가 확인이 필요한 사항: 국내 현장에 적용할 때 해외 기준과 제조사 매뉴얼을 어떤 위계로 해석할지 확인이 필요하다.
- 검토 의견: 도메인 전문가 검토 권장. 안전 관련 case라 문서 근거는 강하지만 최종 적용 기준은 전문가 확인이 안전하다.
- 검토 신뢰도: 높음.

### retrieval_eval_026

- 현재 Relevant Chunk가 질문에 직접 답하는지: `relevant_chunk_ids`가 비어 있어 적절하다.
- Partially Relevant가 더 적절한지: `kdhc_inspection_extract__p044__c01`는 원격검침 항목의 일반 기준 설명으로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 특정 S-14 예정일은 corpus에 없다는 설명이 적절하다.
- 추가 확인이 필요한 사항: 현장 프로젝트 데이터가 별도 시스템에 있다면 이 질문은 RAG가 아니라 운영 DB/API 영역으로 분리해야 한다.
- 검토 의견: 권장. unanswerable label을 유지하는 것이 적절해 보인다.
- 검토 신뢰도: 높음.

### retrieval_eval_027

- 현재 Relevant Chunk가 질문에 직접 답하는지: `relevant_chunk_ids`가 비어 있어 적절하다.
- Partially Relevant가 더 적절한지: `kdhc_inspection_extract__p033__c01`는 PDCV 도압관 기준 설명으로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 기준 설명은 가능하지만 현재 현장 적합/부적합 판정은 불가능하다는 취지가 적절하다.
- 추가 확인이 필요한 사항: 평가 답변에서 현장 사진/도면/점검 기록을 요청하도록 expected answer를 유지하는 것이 좋다.
- 검토 의견: 권장. unanswerable label을 유지하는 것이 적절해 보인다.
- 검토 신뢰도: 높음.

### retrieval_eval_011

- 현재 Relevant Chunk가 질문에 직접 답하는지: 대체로 직접 답한다.
- Partially Relevant가 더 적절한지: `fault_priority_extract__p004__c01`와 `fault_priority_extract__p005__c01`는 FMEA와 rating dimension 설명에 직접 관련되어 relevant가 타당해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: FMEA, occurrence, monitoring potential, maintenance capability 설명은 일치하는 편이다.
- 추가 확인이 필요한 사항: risk score라는 표현이 실제 시스템 score인지 논문 방법론인지 혼동되지 않게 해야 한다.
- 검토 의견: 확인 필요. 평가 질문의 risk score를 live score가 아닌 priority rationale로 제한하면 현재 label이 적절하다.
- 검토 신뢰도: 중간.

### retrieval_eval_016

- 현재 Relevant Chunk가 질문에 직접 답하는지: 대체로 직접 답한다.
- Partially Relevant가 더 적절한지: 두 IEA chunk가 brazed/gasket heat exchanger 비교를 함께 구성하므로 복수 relevant로 유지할 수 있어 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: brazed unit과 gasket type 선택 맥락은 원문과 잘 맞는다.
- 추가 확인이 필요한 사항: swimming pool/chlorinated water 예시가 현재 HeatGrid 운영 범위에서 중요한 평가 질문인지 확인하면 좋다.
- 검토 의견: 권장. 비교형 retrieval case로 유효해 보인다.
- 검토 신뢰도: 높음.

### retrieval_eval_001

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: 현재 partial 후보는 troubleshooting manual과 strainer design context로 보조 근거에 가깝다.
- Expected Answer Points가 Chunk 원문과 일치하는지: no heat, clogged strainer/filter, differential pressure controller, air pockets는 원문과 일치한다.
- 추가 확인이 필요한 사항: `danfoss_substation_operation_extract__p023__c01`는 같은 내용을 더 넓게 담고 있어 relevant 승격 여부를 검토할 수 있다.
- 검토 의견: 권장. 현재 relevant label은 적절해 보인다.
- 검토 신뢰도: 높음.

### retrieval_eval_002

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: pump manual page와 DHW operation page는 보조 근거로 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: pump running, power supply, air in pump housing 점검은 원문과 일치한다.
- 추가 확인이 필요한 사항: 순환펌프와 난방펌프 문맥이 섞이지 않도록 partial 후보를 확인하면 좋다.
- 검토 의견: 권장. 현재 label 유지가 적절해 보인다.
- 검토 신뢰도: 높음.

### retrieval_eval_003

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: row010/row011은 같은 DHW 저온 증상군이지만 mixer non-return valve 직접 근거는 아니므로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: thermostatic mixer non-return valve, mixing, other tapping points fluctuation은 일치한다.
- 추가 확인이 필요한 사항: 한국어 "역류방지밸브"와 원문 "non-return valve"의 도메인 용어 대응을 확인하면 좋다.
- 검토 의견: 확인 필요. 용어 대응만 검수하면 label은 강해 보인다.
- 검토 신뢰도: 높음.

### retrieval_eval_004

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: maintenance page는 열교환기 청소 맥락이므로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: capillary tube air, calcified plate heat exchanger, vent/replace 조치는 원문과 일치한다.
- 추가 확인이 필요한 사항: "replace plate heat exchanger"를 답변에 포함할 때 현장 확정 조치가 아니라 후보 조치로 표현해야 한다.
- 검토 의견: 권장. 현재 relevant label은 적절하나 표현 안전성 검수가 필요하다.
- 검토 신뢰도: 높음.

### retrieval_eval_005

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: startup quick guide는 보조 절차로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: retighten, filling, pressure test, after heating check는 원문과 일치한다.
- 추가 확인이 필요한 사항: Danfoss manual 기준이 현장 표준 절차와 충돌하지 않는지 확인하면 좋다.
- 검토 의견: 권장. 현재 label 유지가 적절해 보인다.
- 검토 신뢰도: 높음.

### retrieval_eval_007

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p034/p044는 인접 항목이므로 partial로 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 1차측 열량계 관경/설치위치, 스트레이너 규격/설치상태는 원문과 일치한다.
- 추가 확인이 필요한 사항: 준공점검 전체 맥락에서 해당 항목이 누락 없이 표현되었는지 확인하면 좋다.
- 검토 의견: 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_008

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p007/p022는 절차와 서식 배경이므로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 7일 전 신청, 접수 채널, 미비시 재점검은 원문과 일치한다.
- 추가 확인이 필요한 사항: 현행 기준 개정 여부는 정적 corpus 밖이므로 별도 확인 대상이다.
- 검토 의견: 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_009

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p034도 strainer와 PDCV 역할을 다루므로 relevant 승격 여부를 확인할 수 있다.
- Expected Answer Points가 Chunk 원문과 일치하는지: DPV 바이패스 배관, 동일 관경, DPV 전 스트레이너 확인은 원문과 일치한다.
- 추가 확인이 필요한 사항: DPV와 PDCV 용어가 질문/문서에서 혼용되지 않는지 확인하면 좋다.
- 검토 의견: 확인 필요. p034의 위치를 partial로 둘지 relevant로 올릴지 검수 권장.
- 검토 신뢰도: 중간.

### retrieval_eval_010

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답하는 것으로 보인다.
- Partially Relevant가 더 적절한지: p034는 PDCV 역할 배경이므로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 공급측/회수측 도압관 연결 기준과 측면 연결 선호는 원문과 일치한다.
- 추가 확인이 필요한 사항: 도압관 연결 위치 해석은 도메인 용어가 중요하므로 전문가 확인이 필요하다.
- 검토 의견: 도메인 전문가 검토 권장.
- 검토 신뢰도: 중간.

### retrieval_eval_013

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p008은 prioritised faults context이므로 partial로 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: motorised control valve, actuator travel time, ranking values는 원문과 일치한다.
- 추가 확인이 필요한 사항: PDF extraction의 숫자 순서와 의미를 원문 표로 확인하면 좋다.
- 검토 의견: 확인 필요. numeric extraction 검수 후 approved를 고려하는 것이 좋다.
- 검토 신뢰도: 중간.

### retrieval_eval_015

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p072와 Danfoss control page는 배경 근거로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: two-port valve, electric/self-acting control, precision/service life/minimum maintenance는 일치한다.
- 추가 확인이 필요한 사항: section title이 PDF extraction 때문에 fragmentary하므로 chunk 원문 중심으로 검수해야 한다.
- 검토 의견: 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_017

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p042는 제어장치 배경이므로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 급탕 과부하시 난방용 온도조절밸브 순간 차단 제어회로는 원문과 일치한다.
- 추가 확인이 필요한 사항: "순간 차단" 표현이 운영 답변에서 과격하게 해석되지 않도록 원문 기준으로 표현해야 한다.
- 검토 의견: 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_018

- 현재 Relevant Chunk가 질문에 직접 답하는지: 대체로 직접 답한다.
- Partially Relevant가 더 적절한지: p031은 안전밸브 관련 배경이므로 partial로 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: Vent/Drain, Air Vent Valve 위치 기준은 일치하지만 원문 추출이 일부 끊겨 있다.
- 추가 확인이 필요한 사항: PDF/curated 원문에서 잘린 절을 확인해야 한다.
- 검토 의견: 도메인 전문가 검토 권장. 안전/배관 위치 기준이고 extraction truncation이 있어 최종 검수 필요.
- 검토 신뢰도: 중간.

### retrieval_eval_019

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p036은 열교환기 세부 기준으로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 용량, 승인용량 확인, 배관경 확인, 판형열교환기 모델명/열판 수 표기는 원문과 일치한다.
- 추가 확인이 필요한 사항: "준공점검 서식" 범위 내에서 난방순환펌프와 판형열교환기 항목이 같은 chunk에 충분히 들어 있는지 확인하면 좋다.
- 검토 의견: 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_020

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p048은 시공절차 배경, Swedish welding chunk는 국제 기준 비교로 partial/confusable 경계 확인이 필요하다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 후면비드, TIG 또는 MIG, 시공자격ID 요구는 원문과 일치한다.
- 추가 확인이 필요한 사항: 용접 기준은 안전/자격 이슈가 있어 국내 기준 원문 확인이 필요하다.
- 검토 의견: 도메인 전문가 검토 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_021

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: troubleshooting manual과 pump page는 보조 근거로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: thermostat, actuator, controller, power outage, pump, air pocket 후보는 원문과 일치한다.
- 추가 확인이 필요한 사항: 유사 사례 category이므로 원인 확정 표현을 피하도록 forbidden claims를 유지해야 한다.
- 검토 의견: 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_022

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: row008은 같은 "long wait for hot water" 증상의 다른 원인이므로 partial로 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: clogged DH supply strainer, DHW controller, PTC2 sensor는 원문과 일치한다.
- 추가 확인이 필요한 사항: row008과 row009를 answer에서 혼합할 때 pump 원인과 controller/sensor 원인을 구분해야 한다.
- 검토 의견: 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_023

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: IEA schematic chunk는 connection context 보조 근거로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: parallel/two-stage connection과 return temperature 설명은 원문과 일치한다.
- 추가 확인이 필요한 사항: category가 `operating_standard`, query_intent가 `comparison`인 구조가 분석 목적에 맞는지 확인하면 좋다.
- 검토 의견: 확인 필요. category/query_intent 설계는 유지 가능하지만 분석 시 comparison으로 따로 집계할 필요가 있다.
- 검토 신뢰도: 높음.

### retrieval_eval_024

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: Danfoss startup/connection pages는 보조 절차로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: balancing, record results, function checking, temperature measurement, tightening은 일치한다.
- 추가 확인이 필요한 사항: Swedish commissioning 기준과 제조사 startup guide를 답변에서 구분해야 한다.
- 검토 의견: 권장.
- 검토 신뢰도: 높음.

### retrieval_eval_025

- 현재 Relevant Chunk가 질문에 직접 답하는지: 직접 답한다.
- Partially Relevant가 더 적절한지: p012는 열량계/계기류 배경으로 partial이 적절해 보인다.
- Expected Answer Points가 Chunk 원문과 일치하는지: 원격검침 선로상태, 기계실 연결 여부, 통신준공 예정일 확인은 일치한다.
- 추가 확인이 필요한 사항: 질문에 "계기류"가 있어 p044만으로 충분한지 확인하면 좋다.
- 검토 의견: 확인 필요. 질문 범위를 원격검침으로 좁히거나 추가 chunk를 검토할 수 있다.
- 검토 신뢰도: 중간.
