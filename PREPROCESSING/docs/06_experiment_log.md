# 06 Experiment Log

## 목적

06 실험 문서를 한 장에서 찾을 수 있도록 risk / leadtime 실험을 묶어 둔 인덱스다.

## canonical 실행 파일

```text
PREPROCESSING/osj/06_risk_experiments.py
PREPROCESSING/osj/06_leadtime_experiments.py
```

## risk 실험 묶음

```text
event_reencoding        -> 06_event_context_reencoding_experiment.py
event_state             -> 06_event_context_state_experiment.py
thermal                 -> 06_thermal_feature_experiment.py
state_thermal_combined  -> 06_state_thermal_combined_experiment.py
weighting               -> 06_risk_weighting_experiment.py
combined_feature        -> 06_combined_feature_experiment.py
```

실제 위치:

```text
PREPROCESSING/osj/experiments/06_test/
```

## leadtime 실험 묶음

```text
leadtime_improvements   -> 06_leadtime_improvement_experiments.py
```

실제 위치:

```text
PREPROCESSING/osj/experiments/06_test/
```

## 주요 결론 요약

### risk

```text
1. event-context state feature는 FN 감소에 의미가 있었다.
2. thermal 조합도 일부 효과가 있었다.
3. state + thermal combined는 FN 감소는 좋았지만 FPR 상승이 컸다.
4. weighting은 FN 감소 효과는 있었지만 공식 calibrated 본 대체에는 부족했다.
5. 결론적으로 risk 공식본은 calibrated 유지가 맞다.
```

### leadtime

```text
1. 3버킷 유지가 가장 현실적이었다.
2. timeflow lag/delta/roll3 조합이 소폭 개선을 만들었다.
3. promoted leadtime 본은 기존 대비 macro_f1이 소폭 개선되었다.
```

## 세부 문서

```text
PREPROCESSING/docs/06_event_context_reencoding_experiment.md
PREPROCESSING/docs/06_event_context_state_experiment.md
PREPROCESSING/docs/06_thermal_feature_experiment.md
PREPROCESSING/docs/06_state_thermal_combined_experiment.md
PREPROCESSING/docs/06_risk_weighting_experiment.md
PREPROCESSING/docs/06_combined_feature_experiment.md
PREPROCESSING/docs/06_leadtime_improvement_experiments.md
```

legacy notebook 기반 비교 자료:

```text
PREPROCESSING/docs/06_test/06_event_context_ablation.md
PREPROCESSING/osj/experiments/06_test/06_event_context_ablation.ipynb
```


