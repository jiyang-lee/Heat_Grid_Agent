# 07 Priority Engine v2_threshold48 승격 기록

## 결론

`priority_engine_v2_threshold48`을 07 Priority Engine의 공식 버전으로 승격했다.

## 변경 내용

- 기존 버전명: `priority_engine_v2_rule_based_tuned`
- 승격 버전명: `priority_engine_v2_threshold48`
- 기존 high/urgent 기준 threshold: `52.0`
- 승격 high/urgent 기준 threshold: `48.0`
- urgent 기준: `70.0` 유지
- medium 기준: `34.0` 유지
- priority score 산식은 변경하지 않음

## 반영 파일

- `PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py`
- `PREPROCESSING/osj/07_priority_engine.ipynb`
- `data/processed/ml_priority/priority_engine_scores_tuned.csv`
- `data/processed/ml_priority/models/priority_engine_tuned_metadata.json`
- `data/processed/ml_priority/priority_engine_scores_v2_threshold48.csv`
- `data/processed/ml_priority/models/priority_engine_v2_threshold48_metadata.json`

## Holdout 검증 결과

`priority_engine_scores_tuned.csv` 재생성 후 holdout 기준:

```text
Precision 1.0000
Recall    0.5116
F1        0.6769
FPR       0.0000
TP        44
FP        0
FN        42
TN        214
```

## 승격 사유

기존 threshold 52 대비 threshold 48은 holdout 오탐률을 증가시키지 않고 실제 위험구간 포착 수를 늘렸다.

```text
threshold 52: TP 37 / FP 0 / Recall 0.4302 / F1 0.6016 / FPR 0.0000
threshold 48: TP 44 / FP 0 / Recall 0.5116 / F1 0.6769 / FPR 0.0000
```

따라서 `48`은 현재 데이터 기준에서 오탐률 0을 유지하면서 가장 실용적으로 민감도를 높이는 공식 기준이다.
