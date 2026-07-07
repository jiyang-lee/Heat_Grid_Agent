# Current-best 지원 산출물

이 폴더는 최종 M1 패키지가 current-best 결과를 어떤 근거로 받아왔는지 설명하기 위한 보존 영역이다. active agent output은 `output/`에 있고, 여기의 파일은 비교, 추적성, 재검토용 근거다.

## 폴더 구조

```text
ARTIFACT_INDEX.csv                         복사된 산출물 전체 인덱스
source_score_outputs/                      best_score bridge의 원본 risk/leadtime/priority/anomaly score
reports/risk/                              risk 최종 metric, threshold, feature audit, episode summary
reports/leadtime/                          leadtime 최종 metric, confusion matrix, ablation, feature audit
reports/priority/                          priority ranking 및 substation ranking 비교
reports/anomaly/                           anomaly metric, validity audit, multi-window/raw-point 요약 metric
reports/operational/                       operational policy 비교와 평가 보고서
contracts/                                 current-best feature/raw/agent data contract
model_metadata/                            current-best 모델 및 priority engine metadata
experiment_traces/risk/                    risk 후보/threshold/ablation/오류 분석 trace
experiment_traces/leadtime/                leadtime 후보/promoted 모델 trace
experiment_traces/anomaly_baseline/        anomaly baseline 후보/threshold trace
experiment_traces/report_compare/          최종 비교 notebook이 참조한 risk/leadtime/anomaly/priority 비교 CSV
experiment_traces/priority_compare/        priority rule vs LGBM 비교 metric/report
```

## 해석 기준

- `source_score_outputs/`는 `src/third_model/best_bridge.py`가 M1 범위로 필터링하는 원본이다.
- `reports/`는 최종 current-best가 왜 선택되었는지 보는 요약/진단 산출물이다.
- `experiment_traces/`는 risk, leadtime, anomaly의 후보 비교와 promoted 선택 근거다.
- raw data 전체와 폐기된 대형 실험 모델 바이너리는 포함하지 않았다. 패키지 인수자가 흐름과 판단 근거를 이해하는 데 필요한 생성 산출물 중심으로 남겼다.
