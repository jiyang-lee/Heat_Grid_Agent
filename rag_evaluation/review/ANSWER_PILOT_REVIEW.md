# Answer Generation Pilot 사람 검수 자료

이 문서는 `answer_generation_pilot.jsonl` 5건을 사람이 검수하기 위한 자료다. AI 의견은 별도 `ANSWER_PILOT_AI_COMMENTS.md`에 분리되어 있으며, 이 문서는 자동 승인 또는 자동 판정을 수행하지 않는다.

## 검수 목적

- Pilot 답변이 `EVALUATION_POLICY.md`와 `ANSWER_REVIEW_RUBRIC.md` 기준을 만족하는지 확인한다.
- `generated_answer`가 retrieved context에 충실한지 확인한다.
- `cited_chunk_ids`가 답변의 핵심 주장을 실제로 뒷받침하는지 확인한다.
- Retrieval Miss 또는 answerable=false 상황에서 무리한 답변이나 과도한 citation이 없는지 확인한다.

## 검수 항목 안내

- Faithfulness: 답변의 핵심 주장이 retrieved context에서 직접 뒷받침되는지 확인한다.
- Hallucination 여부: 근거 없는 고장 확정, 수치 생성, 현장 확인 결과, 작업 완료 주장이 있는지 확인한다.
- Operational Usefulness: 운영자가 다음 확인 행동을 안전하게 이해할 수 있는지 확인한다.
- Citation Accuracy: cited chunk가 답변 주장을 직접 뒷받침하는지 확인한다.
- Citation Completeness: 핵심 주장에 필요한 citation이 충분한지 확인한다.
- Answer Relevance: 답변이 질문에 직접 답하고 불필요한 내용을 줄였는지 확인한다.
- Unanswerable Handling: answerable=false 또는 Retrieval Miss 상황에서 적절히 유보했는지 확인한다.
- 안전 표현 준수: 가능성, 확인 필요, 근거 부족, 추가 문서 또는 현장 확인 필요 표현이 적절한지 확인한다.

## Reviewer 입력값

- `faithfulness_score`: 1~5
- `operational_usefulness_score`: 1~5
- `citation_accuracy_score`: 1~5
- `answer_relevance_score`: 1~5
- `hallucination_severity`: none / minor / moderate / severe / critical
- `reviewer_decision`: pass / revise / reject / needs_domain_review
- `reviewer_comment`: 검수자가 판단 근거와 수정 필요 사항을 자유롭게 기록

## retrieval_eval_001

중점 검토: Retrieval Hit + keyword_match: 검색 근거를 실제로 활용했는지 확인

### Case Metadata

| 항목 | 값 |
|---|---|
| case_id | `retrieval_eval_001` |
| query | 난방이 전혀 안 될 때 스트레이너 막힘이나 차압제어 이상을 원인 후보로 봐도 돼? |
| retrieval_hit_at_5 | True |
| answerable | True |
| query_type | `keyword_match` |
| query_intent | `fault_cause` |
| retrieved_chunk_ids | `danfoss_troubleshooting_table__row001, danfoss_troubleshooting_table__row002, danfoss_troubleshooting_table__row003, danfoss_troubleshooting_table__row004, danfoss_troubleshooting_table__row005` |
| cited_chunk_ids | `danfoss_troubleshooting_table__row001` |

### generated_answer

> 네, 검색된 근거상 난방이 전혀 안 되는 경우 원인 후보로 스트레이너/필터 막힘과 차압제어기 이상을 볼 수 있습니다. 다만 현재 근거만으로는 실제 원인으로 확정할 수는 없고, 필터 청소와 차압제어기 기능 확인이 필요합니다. 또한 시스템 내 공기 혼입도 함께 원인 후보로 제시되어 있습니다.

### expected_answer_points

- No heat can be associated with clogged dirt strainers or filters.
- A defective or incorrectly set differential pressure controller is also listed as a possible cause.
- The answer should keep the cause as a candidate, not a confirmed diagnosis.

### forbidden_claims

- Do not state the strainer is definitely clogged.
- Do not invent measured differential pressure.
- Do not claim a technician already cleaned the filter.

### Cited Context 원문

#### Rank 1 / `danfoss_troubleshooting_table__row001`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: No heat
Possible cause: Dirt strainer in the district heating or
heating return line clogged.
Filter in district heating meter clogged.
Defective or incorrectly set differential
pressure controller.
Air pockets in the system.
Recommended action: Clean the filter/dirt strainer.
Cean the filter (in consultation with the
district heating plant).
Check the functions of the differential
pressure controller - if necessary, clean the
valve seat.
Vent the system thoroughly - see the
instructions.
Component: strainer/filter
```

### Retrieved Context 전체 원문

#### Rank 1 / `danfoss_troubleshooting_table__row001`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: No heat
Possible cause: Dirt strainer in the district heating or
heating return line clogged.
Filter in district heating meter clogged.
Defective or incorrectly set differential
pressure controller.
Air pockets in the system.
Recommended action: Clean the filter/dirt strainer.
Cean the filter (in consultation with the
district heating plant).
Check the functions of the differential
pressure controller - if necessary, clean the
valve seat.
Vent the system thoroughly - see the
instructions.
Component: strainer/filter
```

#### Rank 2 / `danfoss_troubleshooting_table__row002`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: Uneven distribution of heat
Possible cause: Air pockets in the system.
Recommended action: Vent the system thoroughly - see the
instructions.
Component: air/venting
```

#### Rank 3 / `danfoss_troubleshooting_table__row003`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: Uneven distribution of heat
Possible cause: Insufficient heating surface / radiators
too small compared to the total heating
requirement of the building.
Poor utilisation of the existing heating
sursurface.
Recommended action:
Component: general
```

#### Rank 4 / `danfoss_troubleshooting_table__row004`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: No heat
Possible cause: Defective thermostat (sensor).
Defective actuator - or possibly dirt in
the valve housing.
Automatic components/controller
incorrectly adjusted or defective - or
possibly power outage.
The pump is not working.
The pump is set at too low speed of
rotation (not all system types).
Air pockets in the system.
Recommended action: Replace sensor.
Check that the actor is functioning
correctly - clean the valve seat if necessary.
Check that the controller setting is correct
- see the separate instructions for the con-
troller.
Check the power supply.
Temporarily set the actuator to “manual”
control - see the instructions for the heat-
ing system.
Check that there is a power supply for the
pump, and that it is operating.
Check that there is no air in the pump
housing - see pump manual.
Set the pump to a higher speed - see the
instructions for the heating system.
Vent the installation thoroughly - see the
instructions.
Component: pump
```

#### Rank 5 / `danfoss_troubleshooting_table__row005`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: DHW*, no hot water
Possible cause: Non-return valve in the circulation pipe
defective (leads to mixing - the circula-
tion water pipes become cold during
tapping).
Recommended action: Replace the non-return valve.
Component: control valve/actuator/controller
```

### 사람 검수 입력칸

| 항목 | 입력 |
|---|---|
| faithfulness_score (1~5) |  |
| operational_usefulness_score (1~5) |  |
| citation_accuracy_score (1~5) |  |
| answer_relevance_score (1~5) |  |
| hallucination_severity |  |
| reviewer_decision |  |
| reviewer_comment |  |

### Reviewer 확인 질문

- 답변의 핵심 주장이 retrieved context로 직접 뒷받침되는가?
- 근거 없는 고장 확정, 수치 생성, 현장 확인 결과, 작업 완료 주장이 있는가?
- Citation이 핵심 주장에 직접 연결되는가, 아니면 배경 정보에 가깝거나 약한 관련성인가?
- Retrieval Miss 또는 answerable=false 상황에서 충분히 유보했는가?
- Answer Relevance 관점에서 질문의 핵심 의도에 직접 답했는가?
- Reviewer Comment에 수정 필요 사항이나 도메인 검토 필요성을 기록해야 하는가?

## retrieval_eval_015

중점 검토: Retrieval Hit + semantic_paraphrase: 의미가 다른 표현에서도 답변이 근거에 충실한지 확인

### Case Metadata

| 항목 | 값 |
|---|---|
| case_id | `retrieval_eval_015` |
| query | two-port control valve를 쓰는 이유와 self-acting/electric control valve 선택 기준을 설명할 근거가 있어? |
| retrieval_hit_at_5 | True |
| answerable | True |
| query_type | `semantic_paraphrase` |
| query_intent | `operating_standard` |
| retrieved_chunk_ids | `danfoss_substation_operation_extract__p016__c01, danfoss_substation_operation_extract__p005__c01, fault_priority_extract__p007__c01, iea_sh_dhw_substation_extract__p073__c01, danfoss_substation_operation_extract__p014__c01` |
| cited_chunk_ids | `iea_sh_dhw_substation_extract__p073__c01` |

### generated_answer

> 검색된 근거로는 설명할 수 있습니다. IEA 자료에 따르면 two-port control valve는 일반적으로 열교환기 내 물을 한 번만 순환시키는 것이 더 경제적이어서 three-port 대신 사용합니다. 또한 제어밸브는 전동식(electrically driven) 또는 self-acting(외부 전원 없음) 방식이 가능하며, 선택 시에는 건물 부하에 맞는 용량, 높은 rangeability, 낮은 leakage, 빠른 응답성과 같은 조건을 고려해야 합니다. 다만 self-acting과 electric control valve의 구체적인 선택 기준을 더 상세히 설명하려면 추가 문서 확인이 필요합니다.

### expected_answer_points

- Two-port control valves are generally used rather than three-port because circulating water through the heat exchanger only once is economical.
- Control valves can be electrically driven or self-acting with temperature sensors.
- Selection should consider precise control, service life, and minimum maintenance according to extracted text.

### forbidden_claims

- Do not state one valve type is always mandatory for all systems.
- Do not invent manufacturer-specific model requirements.
- Do not provide a site design without design data.

### Cited Context 원문

#### Rank 4 / `iea_sh_dhw_substation_extract__p073__c01`

- document_title: IEA DHC Connection Handbook - Selected DH/Substation Extract
- section_title: selected for more precise control, longer service life and minimum maintenance.
- rag_role: dhc_structure_handbook
- score: 9

```text
Two-port control valves are used rather than three-port because in general, it is most economical to
circulate the water in the heat exchanger only once.
Control valves can be either electrically driven or self-acting with no external power supply. All
control valves should be capable of being manually overridden, providing the operator with the
option of controlling the flow.
Control valves on domestic hot water heat exchangers must be designed to close upon a power
failure. In cases where too high a water temperature is critical, a non-resetting valve should be
placed in the common ‘secondary’ flow operating on loss of power as well as over temperature.
Temperature sensors should be located close to the exchangers being controlled in order to get a
fast reacting control system.
It is imperative that the heat exchanger control valves be selected to match the building loads as
oversizing will reduce valve life and cause valve hunting. Control valves should be selected with
high rangeability, low leakage, and proportional plus integrating control for close adjustment,
balancing, temperature accuracy and response time. Control valves should have enough power to
open and close under...
```

### Retrieved Context 전체 원문

#### Rank 1 / `danfoss_substation_operation_extract__p016__c01`

- document_title: Danfoss Akva Lux II VXe Manual - Selected Operation and Maintenance Extract
- section_title: 12. CONTROL OF HEATING CIRCUIT
- rag_role: troubleshooting_manual
- score: 10

```text
12. CONTROL OF HEATING CIRCUIT
Self-acting flow controller with integrated control valve and ac AVQM AMV 150
tuator - Manual override
For controlling the heating circuit the Akva Lux II VXe is supplied with
a self-acting flow controller with integrated control valve Danfoss
AVQM and a Danfoss AMV actuator placed in the primary return flow
line. The AMV actuator is electrically wired to the controller from
the plant.
The control valve closes on rising differential pressure and opens on
falling differential pressure to control max flow. The controller closes
when set max. flow is exceeded.
Press and hold the button (on
In a combination with electrical actuators AMV and ECL electronic the bottom side of the actuator)
during manual operation.
controllers the flow and temperature can be controlled to achieve
highest energy savings. The controller is equipped with excess pres-
sure safety valve, which protects control diaphragm for flow control
from too high differential pressure.
AMV 150
The actuator has undergone a functional test and is preset from
factory.
In the event of operating disturbances the actuator can be shut off
manually by turning the manual override knob on top of the a...
```

#### Rank 2 / `danfoss_substation_operation_extract__p005__c01`

- document_title: Danfoss Akva Lux II VXe Manual - Selected Operation and Maintenance Extract
- section_title: 3. GETTING STARTED - QUICK GUIDE FOR EASY START-UP
- rag_role: troubleshooting_manual
- score: 9

```text
3. GETTING STARTED - QUICK GUIDE FOR EASY START-UP
Mounting
Note!
Connect the substation to the household piping in accordance with
Heating and cooling the substation may cause leaks. Therefore
the labelling at the bottom and/or in accordance with the instructions
in this manual. it may be necessary to retighten the connections in the period
after commissioning.
If the household piping system features domestic hot water
recirculation, the substation must be connected to the recirculation Note!
system. The circulation set for recirculation connection is not standard Never lift the station by its front insulation cover!
equipment. The set must be purchased as extra equipment.
We recommend establishing recirculation BEFORE mounting the
substation on the wall.
For instructions about recirculation connection, see page 14.
GETTING STARTED is a quick guide and some details in connection with
installation and commissioning may require additional information,
which can be found elsewhere in this instruction manual.
GETTING STARTED AKVA LUX II VXe
If the household piping system features domestic hot water recircula-
tion, the substation must be connected to the recirculation system,
- accor...
```

#### Rank 3 / `fault_priority_extract__p007__c01`

- document_title: Prioritisation of faults in district heating substations - Selected Extract
- section_title: Monitoring & Maintenance potential: air in the piping system has a This study has presented a novel methodology for the prioritisation
- rag_role: fault_priority_research
- score: 9

```text
Fig. 3. Frequency distribution of MPNs.
unit and the wrong placement of the outdoor temperature sensor. 5. Conclusions
Other faults, which are at the bottom of the list, have a relative low
Monitoring & Maintenance potential: air in the piping system has a This study has presented a novel methodology for the prioritisation
monitoring potential (grey bar) of 2.1, meaning it can only be detected of faults, aimed at supporting the optimisation of O&M. The methodol-
after the fault occurred and only with additional efforts; and two faults ogy, which is based on the FMEA process, introduces a monitoring and
associated with the three-way valve for domestic hot water have a maintenance evaluation factor. Based on a literature review of previous
maintenance capability (yellow bar) of around 2, meaning they can research, the relevant faults of district heating substations in the north
be repaired but only through corrective actions after fault occurred. European countries have been extended including the experiences in
And finally, 5 faults have a high potential for predictive maintenance. German district heating. The rating criteria for substations has been
These are poor flow rate throug...
```

#### Rank 4 / `iea_sh_dhw_substation_extract__p073__c01`

- document_title: IEA DHC Connection Handbook - Selected DH/Substation Extract
- section_title: selected for more precise control, longer service life and minimum maintenance.
- rag_role: dhc_structure_handbook
- score: 9

```text
Two-port control valves are used rather than three-port because in general, it is most economical to
circulate the water in the heat exchanger only once.
Control valves can be either electrically driven or self-acting with no external power supply. All
control valves should be capable of being manually overridden, providing the operator with the
option of controlling the flow.
Control valves on domestic hot water heat exchangers must be designed to close upon a power
failure. In cases where too high a water temperature is critical, a non-resetting valve should be
placed in the common ‘secondary’ flow operating on loss of power as well as over temperature.
Temperature sensors should be located close to the exchangers being controlled in order to get a
fast reacting control system.
It is imperative that the heat exchanger control valves be selected to match the building loads as
oversizing will reduce valve life and cause valve hunting. Control valves should be selected with
high rangeability, low leakage, and proportional plus integrating control for close adjustment,
balancing, temperature accuracy and response time. Control valves should have enough power to
open and close under...
```

#### Rank 5 / `danfoss_substation_operation_extract__p014__c01`

- document_title: Danfoss Akva Lux II VXe Manual - Selected Operation and Maintenance Extract
- section_title: 10. ADJUSTMENT AND COMMISSIONING
- rag_role: troubleshooting_manual
- score: 7

```text
10. ADJUSTMENT AND COMMISSIONING
General information
PLEASE NOTE! Some models may have a slightly different appear-
ance, but the control function is in principle the same as described
below.
Commissioning
Commission the substation in accordance with the instruction
manual.
Filling the system / operating pressure
Fill the unit with water according to the instructions on page 11.
If the pressure drops below 1 bar, water must be added to the sys-
tem.
The operating pressure should never exceed 1.5 bar.
(The safety valve opens at 2,5 bar).
The pressure is read on the manometer.
If system pressure drops dramatically within a short time, heating
system should be examined for leakage, - this includes checking
the factory set pressure of the expansion vessel, which is normally
0,5 bar.
Manometer
Differential pressure controller
For Akva Lux II VXe the differential pressure controller is installed in
the AVQM self-acting flow controller with integrated control valve.
Please see page 16.
AVQM
14 | © Danfoss | Produced by Danfoss Redan A/S | 2021.02 xxxxxxx
```

### 사람 검수 입력칸

| 항목 | 입력 |
|---|---|
| faithfulness_score (1~5) |  |
| operational_usefulness_score (1~5) |  |
| citation_accuracy_score (1~5) |  |
| answer_relevance_score (1~5) |  |
| hallucination_severity |  |
| reviewer_decision |  |
| reviewer_comment |  |

### Reviewer 확인 질문

- 답변의 핵심 주장이 retrieved context로 직접 뒷받침되는가?
- 근거 없는 고장 확정, 수치 생성, 현장 확인 결과, 작업 완료 주장이 있는가?
- Citation이 핵심 주장에 직접 연결되는가, 아니면 배경 정보에 가깝거나 약한 관련성인가?
- Retrieval Miss 또는 answerable=false 상황에서 충분히 유보했는가?
- Answer Relevance 관점에서 질문의 핵심 의도에 직접 답했는가?
- Reviewer Comment에 수정 필요 사항이나 도메인 검토 필요성을 기록해야 하는가?

## retrieval_eval_002

중점 검토: Retrieval Miss + keyword_match: 근거 부족 상태에서 과도하게 답하지 않았는지 확인

### Case Metadata

| 항목 | 값 |
|---|---|
| case_id | `retrieval_eval_002` |
| query | 온수가 늦게 나오면 순환펌프 쪽에서는 무엇을 점검해야 해? |
| retrieval_hit_at_5 | False |
| answerable | True |
| query_type | `keyword_match` |
| query_intent | `inspection_action` |
| retrieved_chunk_ids | `danfoss_troubleshooting_table__row001, danfoss_troubleshooting_table__row002, danfoss_troubleshooting_table__row003, danfoss_troubleshooting_table__row004, danfoss_troubleshooting_table__row005` |
| cited_chunk_ids | `danfoss_troubleshooting_table__row004, danfoss_troubleshooting_table__row005` |

### generated_answer

> 검색된 근거상 순환펌프 쪽에서는 먼저 펌프에 전원 공급이 있는지와 펌프가 실제로 동작하는지 확인해야 합니다. 또한 펌프 하우징에 공기가 없는지 점검하고, 필요하면 펌프 속도를 더 높게 설정하는지 확인할 수 있습니다. 다만 온수가 늦게 나오는 원인이 순환펌프만으로 확정되지는 않으므로 추가 확인이 필요합니다.

### expected_answer_points

- Check whether the circulation pump is running.
- Check whether power is supplied to the pump.
- Check that there is no air in the pump housing.

### forbidden_claims

- Do not say the pump has failed without inspection.
- Do not invent electrical measurements.
- Do not prescribe replacement unless documented evidence supports it.

### Cited Context 원문

#### Rank 4 / `danfoss_troubleshooting_table__row004`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: No heat
Possible cause: Defective thermostat (sensor).
Defective actuator - or possibly dirt in
the valve housing.
Automatic components/controller
incorrectly adjusted or defective - or
possibly power outage.
The pump is not working.
The pump is set at too low speed of
rotation (not all system types).
Air pockets in the system.
Recommended action: Replace sensor.
Check that the actor is functioning
correctly - clean the valve seat if necessary.
Check that the controller setting is correct
- see the separate instructions for the con-
troller.
Check the power supply.
Temporarily set the actuator to “manual”
control - see the instructions for the heat-
ing system.
Check that there is a power supply for the
pump, and that it is operating.
Check that there is no air in the pump
housing - see pump manual.
Set the pump to a higher speed - see the
instructions for the heating system.
Vent the installation thoroughly - see the
instructions.
Component: pump
```

#### Rank 5 / `danfoss_troubleshooting_table__row005`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: DHW*, no hot water
Possible cause: Non-return valve in the circulation pipe
defective (leads to mixing - the circula-
tion water pipes become cold during
tapping).
Recommended action: Replace the non-return valve.
Component: control valve/actuator/controller
```

### Retrieved Context 전체 원문

#### Rank 1 / `danfoss_troubleshooting_table__row001`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: No heat
Possible cause: Dirt strainer in the district heating or
heating return line clogged.
Filter in district heating meter clogged.
Defective or incorrectly set differential
pressure controller.
Air pockets in the system.
Recommended action: Clean the filter/dirt strainer.
Cean the filter (in consultation with the
district heating plant).
Check the functions of the differential
pressure controller - if necessary, clean the
valve seat.
Vent the system thoroughly - see the
instructions.
Component: strainer/filter
```

#### Rank 2 / `danfoss_troubleshooting_table__row002`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: Uneven distribution of heat
Possible cause: Air pockets in the system.
Recommended action: Vent the system thoroughly - see the
instructions.
Component: air/venting
```

#### Rank 3 / `danfoss_troubleshooting_table__row003`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: Uneven distribution of heat
Possible cause: Insufficient heating surface / radiators
too small compared to the total heating
requirement of the building.
Poor utilisation of the existing heating
sursurface.
Recommended action:
Component: general
```

#### Rank 4 / `danfoss_troubleshooting_table__row004`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: No heat
Possible cause: Defective thermostat (sensor).
Defective actuator - or possibly dirt in
the valve housing.
Automatic components/controller
incorrectly adjusted or defective - or
possibly power outage.
The pump is not working.
The pump is set at too low speed of
rotation (not all system types).
Air pockets in the system.
Recommended action: Replace sensor.
Check that the actor is functioning
correctly - clean the valve seat if necessary.
Check that the controller setting is correct
- see the separate instructions for the con-
troller.
Check the power supply.
Temporarily set the actuator to “manual”
control - see the instructions for the heat-
ing system.
Check that there is a power supply for the
pump, and that it is operating.
Check that there is no air in the pump
housing - see pump manual.
Set the pump to a higher speed - see the
instructions for the heating system.
Vent the installation thoroughly - see the
instructions.
Component: pump
```

#### Rank 5 / `danfoss_troubleshooting_table__row005`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: DHW*, no hot water
Possible cause: Non-return valve in the circulation pipe
defective (leads to mixing - the circula-
tion water pipes become cold during
tapping).
Recommended action: Replace the non-return valve.
Component: control valve/actuator/controller
```

### 사람 검수 입력칸

| 항목 | 입력 |
|---|---|
| faithfulness_score (1~5) |  |
| operational_usefulness_score (1~5) |  |
| citation_accuracy_score (1~5) |  |
| answer_relevance_score (1~5) |  |
| hallucination_severity |  |
| reviewer_decision |  |
| reviewer_comment |  |

### Reviewer 확인 질문

- 답변의 핵심 주장이 retrieved context로 직접 뒷받침되는가?
- 근거 없는 고장 확정, 수치 생성, 현장 확인 결과, 작업 완료 주장이 있는가?
- Citation이 핵심 주장에 직접 연결되는가, 아니면 배경 정보에 가깝거나 약한 관련성인가?
- Retrieval Miss 또는 answerable=false 상황에서 충분히 유보했는가?
- Answer Relevance 관점에서 질문의 핵심 의도에 직접 답했는가?
- Reviewer Comment에 수정 필요 사항이나 도메인 검토 필요성을 기록해야 하는가?

## retrieval_eval_003

중점 검토: Retrieval Miss + semantic_paraphrase: 모델 사전지식으로 단정하지 않았는지 확인

### Case Metadata

| 항목 | 값 |
|---|---|
| case_id | `retrieval_eval_003` |
| query | 급탕 온도가 낮고 변동이 있으면 욕실 믹서의 역류방지밸브도 의심 대상이야? |
| retrieval_hit_at_5 | False |
| answerable | True |
| query_type | `semantic_paraphrase` |
| query_intent | `fault_cause` |
| retrieved_chunk_ids | `danfoss_troubleshooting_table__row001, danfoss_troubleshooting_table__row002, danfoss_troubleshooting_table__row003, danfoss_troubleshooting_table__row004, danfoss_troubleshooting_table__row005` |
| cited_chunk_ids | `danfoss_troubleshooting_table__row005` |

### generated_answer

> 검색된 근거만 보면, 급탕(DHW) 관련 문제에서 역류방지밸브(비반환밸브) 이상이 원인일 가능성은 있습니다. 다만 제공된 문서에는 주로 순환배관의 비반환밸브 고장이 ‘급탕 없음’과 관련되어 있고, 질문하신 ‘급탕 온도 저하 및 변동’에 대해 욕실 믹서의 역류방지밸브를 직접 지목하는 근거는 없습니다. 따라서 현재 근거만으로는 욕실 믹서 역류방지밸브를 의심 대상이라고 단정하기 어렵고, 추가 문서 또는 현장 확인이 필요합니다.

### expected_answer_points

- A defective non-return valve in a thermostatic bathroom mixer can cause hot and cold water mixing.
- The document notes fluctuating temperatures may occur at other tapping points.
- The answer should recommend checking mixers for defects as a candidate action.

### forbidden_claims

- Do not claim the bathroom mixer is confirmed defective.
- Do not invent user complaints at other tapping points.
- Do not prescribe non-documented repair steps.

### Cited Context 원문

#### Rank 5 / `danfoss_troubleshooting_table__row005`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: DHW*, no hot water
Possible cause: Non-return valve in the circulation pipe
defective (leads to mixing - the circula-
tion water pipes become cold during
tapping).
Recommended action: Replace the non-return valve.
Component: control valve/actuator/controller
```

### Retrieved Context 전체 원문

#### Rank 1 / `danfoss_troubleshooting_table__row001`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: No heat
Possible cause: Dirt strainer in the district heating or
heating return line clogged.
Filter in district heating meter clogged.
Defective or incorrectly set differential
pressure controller.
Air pockets in the system.
Recommended action: Clean the filter/dirt strainer.
Cean the filter (in consultation with the
district heating plant).
Check the functions of the differential
pressure controller - if necessary, clean the
valve seat.
Vent the system thoroughly - see the
instructions.
Component: strainer/filter
```

#### Rank 2 / `danfoss_troubleshooting_table__row002`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: Uneven distribution of heat
Possible cause: Air pockets in the system.
Recommended action: Vent the system thoroughly - see the
instructions.
Component: air/venting
```

#### Rank 3 / `danfoss_troubleshooting_table__row003`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: Uneven distribution of heat
Possible cause: Insufficient heating surface / radiators
too small compared to the total heating
requirement of the building.
Poor utilisation of the existing heating
sursurface.
Recommended action:
Component: general
```

#### Rank 4 / `danfoss_troubleshooting_table__row004`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: No heat
Possible cause: Defective thermostat (sensor).
Defective actuator - or possibly dirt in
the valve housing.
Automatic components/controller
incorrectly adjusted or defective - or
possibly power outage.
The pump is not working.
The pump is set at too low speed of
rotation (not all system types).
Air pockets in the system.
Recommended action: Replace sensor.
Check that the actor is functioning
correctly - clean the valve seat if necessary.
Check that the controller setting is correct
- see the separate instructions for the con-
troller.
Check the power supply.
Temporarily set the actuator to “manual”
control - see the instructions for the heat-
ing system.
Check that there is a power supply for the
pump, and that it is operating.
Check that there is no air in the pump
housing - see pump manual.
Set the pump to a higher speed - see the
instructions for the heating system.
Vent the installation thoroughly - see the
instructions.
Component: pump
```

#### Rank 5 / `danfoss_troubleshooting_table__row005`

- document_title: Danfoss Troubleshooting Table - Heating and Domestic Hot Water
- section_title: Symptom-cause-action table
- rag_role: symptom_cause_action_table
- score: 4

```text
Symptom: DHW*, no hot water
Possible cause: Non-return valve in the circulation pipe
defective (leads to mixing - the circula-
tion water pipes become cold during
tapping).
Recommended action: Replace the non-return valve.
Component: control valve/actuator/controller
```

### 사람 검수 입력칸

| 항목 | 입력 |
|---|---|
| faithfulness_score (1~5) |  |
| operational_usefulness_score (1~5) |  |
| citation_accuracy_score (1~5) |  |
| answer_relevance_score (1~5) |  |
| hallucination_severity |  |
| reviewer_decision |  |
| reviewer_comment |  |

### Reviewer 확인 질문

- 답변의 핵심 주장이 retrieved context로 직접 뒷받침되는가?
- 근거 없는 고장 확정, 수치 생성, 현장 확인 결과, 작업 완료 주장이 있는가?
- Citation이 핵심 주장에 직접 연결되는가, 아니면 배경 정보에 가깝거나 약한 관련성인가?
- Retrieval Miss 또는 answerable=false 상황에서 충분히 유보했는가?
- Answer Relevance 관점에서 질문의 핵심 의도에 직접 답했는가?
- Reviewer Comment에 수정 필요 사항이나 도메인 검토 필요성을 기록해야 하는가?

## retrieval_eval_026

중점 검토: answerable=false: 유보 표현과 citation 처리 방식이 적절한지 확인

### Case Metadata

| 항목 | 값 |
|---|---|
| case_id | `retrieval_eval_026` |
| query | S-14 기계실의 현재 열량계 통신준공 예정일은 언제야? |
| retrieval_hit_at_5 | False |
| answerable | False |
| query_type | `negative_or_unanswerable` |
| query_intent | `unknown` |
| retrieved_chunk_ids | `kdhc_inspection_extract__p022__c01, kdhc_inspection_extract__p027__c01, danfoss_substation_operation_extract__p005__c01, danfoss_substation_operation_extract__p014__c01, danfoss_substation_operation_extract__p020__c01` |
| cited_chunk_ids | `kdhc_inspection_extract__p022__c01` |

### generated_answer

> 현재 검색된 근거만으로는 S-14 기계실의 열량계 통신준공 예정일을 확인할 수 없습니다. 제공된 문서에는 열량계의 관경이나 점검 기준은 있으나, 통신준공 예정일 정보는 보이지 않습니다. 추가 문서 또는 현장 확인이 필요합니다.

### expected_answer_points

- The static corpus can describe that communication completion or planned completion date should be checked and recorded.
- It cannot know the current S-14 site-specific planned date.
- The answer should request project records or live site data instead of inventing a date.

### forbidden_claims

- Do not invent a date.
- Do not claim access to S-14 project records.
- Do not answer with a generic revision date as if it were the site date.

### Cited Context 원문

#### Rank 1 / `kdhc_inspection_extract__p022__c01`

- document_title: 열사용시설 점검업무 기술 기준서 - 선별 추출본
- section_title: 2.2 열사용시설 중간점검 서식 작성기준<개정 2015. 1.14>
- rag_role: domestic_inspection_standard
- score: 5

```text
2.2 열사용시설 중간점검 서식 작성기준<개정 2015. 1.14>
* 일반사항 : 설계도서 승인시의 일반사항과 동일하게 작성
2.2.1 지구/차수 : 해당지구 및 차수 표기
가. 공동주택 및 공동주택 부대시설은 차수 병행 표기
2.2.2 고객명 : 고객 표기
2.2.3 단지명/세대수 : 블록단위의 단지명 및 세대수 표기
2.2.4 점 검 일 : 점검년월일 표기
2.2.5 기계실번호 : S-1,2,3…(필요시 고객 관리번호와 연계 표기)
※ 일반건물의 경우 기계실 위치 병행 표기(B F 등)
2.2.6 연결열부하 : 승인 연결열부하를 Mcal/hr 단위로 표기
가. 해당 기계실에 대한 한난의 공급부하를 의미<개정 2015. 1.14>
나. 공사비부담금의 부과기준(공동주택 제외)
◦ 공사비부담금의 부과기준은 동계열부하로서 지역냉방 고객의 경우는 승인 연결열부하와
상이할 수 있음
다. 설계도서 승인과정에서 연결열부하, 인입관경, 열량계 관경 등이 결정됨
◦ 별도의 변경신청 절차없이는 변경이 될 수 없음(열사용시설기준 제22조 제3항)
라. 기계실 단위로 한난이 산정하며 인입관, PDCV, 열량계 유량부 관경의 선정기준임
(열사용시설기준 제10조)
2.2.7 승인 인입관경(A) : 기 승인된 해당 기계실의 인입관경을 표기
가. 인입관경 선정기준은 기계실 1차측 인입관경 및 열부하기준표 참조
◦ 동계열부하, 하계열부하 구분
나. 승인관경과 실시공관경(②-1)을 비교
다. 인입연결공사가 한난 대행시공인 경우 대행 시공사명을 함께 기록
2.2.8 열량계(A) : 기 승인된 열량계의 유량부 관경을 표기
가. 열량계의 유량부 관경 선정기준은 기계실 열량계 규격기준표 참조
◦ 설치유량의 100%값을 Qn(연속사용 최대유량)값으로 관경선정
◦ <삭제 2015. 1.14>
◦ <삭제 2015. 1.14>
- 22 -
```

### Retrieved Context 전체 원문

#### Rank 1 / `kdhc_inspection_extract__p022__c01`

- document_title: 열사용시설 점검업무 기술 기준서 - 선별 추출본
- section_title: 2.2 열사용시설 중간점검 서식 작성기준<개정 2015. 1.14>
- rag_role: domestic_inspection_standard
- score: 5

```text
2.2 열사용시설 중간점검 서식 작성기준<개정 2015. 1.14>
* 일반사항 : 설계도서 승인시의 일반사항과 동일하게 작성
2.2.1 지구/차수 : 해당지구 및 차수 표기
가. 공동주택 및 공동주택 부대시설은 차수 병행 표기
2.2.2 고객명 : 고객 표기
2.2.3 단지명/세대수 : 블록단위의 단지명 및 세대수 표기
2.2.4 점 검 일 : 점검년월일 표기
2.2.5 기계실번호 : S-1,2,3…(필요시 고객 관리번호와 연계 표기)
※ 일반건물의 경우 기계실 위치 병행 표기(B F 등)
2.2.6 연결열부하 : 승인 연결열부하를 Mcal/hr 단위로 표기
가. 해당 기계실에 대한 한난의 공급부하를 의미<개정 2015. 1.14>
나. 공사비부담금의 부과기준(공동주택 제외)
◦ 공사비부담금의 부과기준은 동계열부하로서 지역냉방 고객의 경우는 승인 연결열부하와
상이할 수 있음
다. 설계도서 승인과정에서 연결열부하, 인입관경, 열량계 관경 등이 결정됨
◦ 별도의 변경신청 절차없이는 변경이 될 수 없음(열사용시설기준 제22조 제3항)
라. 기계실 단위로 한난이 산정하며 인입관, PDCV, 열량계 유량부 관경의 선정기준임
(열사용시설기준 제10조)
2.2.7 승인 인입관경(A) : 기 승인된 해당 기계실의 인입관경을 표기
가. 인입관경 선정기준은 기계실 1차측 인입관경 및 열부하기준표 참조
◦ 동계열부하, 하계열부하 구분
나. 승인관경과 실시공관경(②-1)을 비교
다. 인입연결공사가 한난 대행시공인 경우 대행 시공사명을 함께 기록
2.2.8 열량계(A) : 기 승인된 열량계의 유량부 관경을 표기
가. 열량계의 유량부 관경 선정기준은 기계실 열량계 규격기준표 참조
◦ 설치유량의 100%값을 Qn(연속사용 최대유량)값으로 관경선정
◦ <삭제 2015. 1.14>
◦ <삭제 2015. 1.14>
- 22 -
```

#### Rank 2 / `kdhc_inspection_extract__p027__c01`

- document_title: 열사용시설 점검업무 기술 기준서 - 선별 추출본
- section_title: 마. Vent/Drain 배관(②-4) : 열사용시설기준 제14조제3항 내지 제6항 규정에 의한 Vent/Drain
- rag_role: domestic_inspection_standard
- score: 5

```text
마. Vent/Drain 배관(②-4) : 열사용시설기준 제14조제3항 내지 제6항 규정에 의한 Vent/Drain
밸브의 설치를 확인하여 표기(적합/부적합)
◦ 공기빼기밸브(Air Vent Valve) 설치기준
- 배관계통별로 1․2차측 구분
- 기기몸체 및 배관상부 설치
- 1차측 주배관의 공기빼기는 기계실 주차단밸브전에 설치(열사용시설기준 별표11참조)
- 1차측 공기빼기 배관은 밸브이후에 배관 연장 필요
◦ 물빼기밸브(Water Drain Valve) 설치기준
- 배관계통별로 1․2차측 구분
- 기기몸체 및 배관하부 설치
- 밸브관경은 20A이상이 바람직함(15A는 이물질로 막힐 수 있음)
◦ 배관구배는 1차측의 경우 기계실 위치가 지하층이므로 하향구배(1/50～1/100), 2차측은
상향구배가 바람직함.
◦ 공기빼기밸브 및 물빼기밸브는 25A이하의 소구경으로써 게이트 및 볼밸브가 바람직하
며 나사이음도 가능하고, 1차측은 KS 20K 또는 ANSI #300이상의 규격이어야 함.
(밸브이후 연장배관은 SPP도 가능)
◦ 트랜치 배관에 연결시 누수 확인이 용이한 구조(깔때기 배관 방식 등)로 시공하여야 함
<개정 2020.12.29.>
바. Hanger/Support(②-5) : 배관의 지지상태 등을 확인하여 적합유무 표기(적합/부적합)
◦ 배관중 반드시 지지가 필요한 곳
- 열교환설비, 펌프 등 기기 연결부위(기기분리 보수시 필요)
- 열량계유량부 주위배관(양측지지 필요)
- 벽체 관통부위(배관자중이 벽체에 영향이 없도록 고정점이 바람직함)
- 횡주관에 대한 일반적인 최대지지간격은 다음과 같음
관경(mm) 20이하 25～40 50 65 80 100 125 150
이상
강관 1.8 2.0 3.0 3.0 3.0 4.0 4.0 4.0 5.0이내
최대간격
(M)
동관 1.0 1.5 2.0 2.5 2.5 2.5 3.0이내 3.0이내 3.0이내
◦ 건물내 1차측 배관의 직선길이가 10m 이상일 경우 검토사항
- 15m이상의 직선배관은 가급적 피할 것(입상, 횡주배관)
- 현장여건상 신축을 보정해 주는 기계적장치(신축이음 조인트 등)를 적용시에는 공인
기관의 성능인증 제품일 것 <개정 2015.1.14>
* 배관의 안정성을 보장하기위한 배관응력 해석 레포트 제출
- 배관지지와 고정점을 반드시 검토할 것(외벽 관통부위를 고정점으로 할 것)
- 건물에서 지하4층 이하의 기계실의 경우 입상피트내 배관의 지지 및 열응력을...
```

#### Rank 3 / `danfoss_substation_operation_extract__p005__c01`

- document_title: Danfoss Akva Lux II VXe Manual - Selected Operation and Maintenance Extract
- section_title: 3. GETTING STARTED - QUICK GUIDE FOR EASY START-UP
- rag_role: troubleshooting_manual
- score: 4

```text
3. GETTING STARTED - QUICK GUIDE FOR EASY START-UP
Mounting
Note!
Connect the substation to the household piping in accordance with
Heating and cooling the substation may cause leaks. Therefore
the labelling at the bottom and/or in accordance with the instructions
in this manual. it may be necessary to retighten the connections in the period
after commissioning.
If the household piping system features domestic hot water
recirculation, the substation must be connected to the recirculation Note!
system. The circulation set for recirculation connection is not standard Never lift the station by its front insulation cover!
equipment. The set must be purchased as extra equipment.
We recommend establishing recirculation BEFORE mounting the
substation on the wall.
For instructions about recirculation connection, see page 14.
GETTING STARTED is a quick guide and some details in connection with
installation and commissioning may require additional information,
which can be found elsewhere in this instruction manual.
GETTING STARTED AKVA LUX II VXe
If the household piping system features domestic hot water recircula-
tion, the substation must be connected to the recirculation system,
- accor...
```

#### Rank 4 / `danfoss_substation_operation_extract__p014__c01`

- document_title: Danfoss Akva Lux II VXe Manual - Selected Operation and Maintenance Extract
- section_title: 10. ADJUSTMENT AND COMMISSIONING
- rag_role: troubleshooting_manual
- score: 4

```text
10. ADJUSTMENT AND COMMISSIONING
General information
PLEASE NOTE! Some models may have a slightly different appear-
ance, but the control function is in principle the same as described
below.
Commissioning
Commission the substation in accordance with the instruction
manual.
Filling the system / operating pressure
Fill the unit with water according to the instructions on page 11.
If the pressure drops below 1 bar, water must be added to the sys-
tem.
The operating pressure should never exceed 1.5 bar.
(The safety valve opens at 2,5 bar).
The pressure is read on the manometer.
If system pressure drops dramatically within a short time, heating
system should be examined for leakage, - this includes checking
the factory set pressure of the expansion vessel, which is normally
0,5 bar.
Manometer
Differential pressure controller
For Akva Lux II VXe the differential pressure controller is installed in
the AVQM self-acting flow controller with integrated control valve.
Please see page 16.
AVQM
14 | © Danfoss | Produced by Danfoss Redan A/S | 2021.02 xxxxxxx
```

#### Rank 5 / `danfoss_substation_operation_extract__p020__c01`

- document_title: Danfoss Akva Lux II VXe Manual - Selected Operation and Maintenance Extract
- section_title: 14. DOMESTIC HOT WATER
- rag_role: troubleshooting_manual
- score: 4

```text
14. DOMESTIC HOT WATER
General information
PLEASE NOTE! Some models may have a slightly different appearance,
but the control function is in principle the same as described below.
Commissioning
Commission the substation in accordance with the instructions in
this manual.
Regulation of domestic hot water temperature
The domestic hot water is prepared in the heat exchanger based on
the flow principle and the temperature is controlled by a combined Fig. 1
hydraulic and thermostatic self-acting controller PTC2+P with in-
tegrated differential pressure controller, which blocks the flow of
primary and secondary side flow through the heat exchanger im-
mediately after completion of the tapping process.
PTC2 controller for DHW (Fig. 1).
Abb.
Adjust the hot water temperature by moving the adjuster lever to-
wards “+” (hotter) or “-” (colder). Start by turning the lever clockwise
Adjuster lever
– until it stops/until you cannot turn it any further. Then turn the lever
counter-clockwise until the temperature of the tap water is approx.
48°C during normal tapping flow (7–8 litres per min.). The temperature
must never exceed 55°C to prevent limescale deposits building up
in the water heater.
B...
```

### 사람 검수 입력칸

| 항목 | 입력 |
|---|---|
| faithfulness_score (1~5) |  |
| operational_usefulness_score (1~5) |  |
| citation_accuracy_score (1~5) |  |
| answer_relevance_score (1~5) |  |
| hallucination_severity |  |
| reviewer_decision |  |
| reviewer_comment |  |

### Reviewer 확인 질문

- 답변의 핵심 주장이 retrieved context로 직접 뒷받침되는가?
- 근거 없는 고장 확정, 수치 생성, 현장 확인 결과, 작업 완료 주장이 있는가?
- Citation이 핵심 주장에 직접 연결되는가, 아니면 배경 정보에 가깝거나 약한 관련성인가?
- Retrieval Miss 또는 answerable=false 상황에서 충분히 유보했는가?
- Answer Relevance 관점에서 질문의 핵심 의도에 직접 답했는가?
- Reviewer Comment에 수정 필요 사항이나 도메인 검토 필요성을 기록해야 하는가?
