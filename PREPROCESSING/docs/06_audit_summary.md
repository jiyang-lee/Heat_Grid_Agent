# 06 Audit Summary

## 목적

06 감사성 파일을 하나의 진입점으로 묶고, 무엇을 보기 위한 감사인지 정리한다.

## canonical 실행 파일

```text
PREPROCESSING/osj/06_risk_audit.py
```

지원 audit:

```text
false_negative      -> 06_false_negative_audit.py
false_negative_deep -> 06_false_negative_deep_audit.py
feature_importance  -> 06_feature_importance_audit.py
group_calibration   -> 06_group_calibration.py
drift_ablation      -> 06_drift_feature_ablation.py
manufacturer2_sh_fp -> 06_manufacturer2_sh_fp_audit.py
```

이 중 `group_calibration`을 제외한 개별 감사 스크립트의 실제 위치:

```text
PREPROCESSING/osj/06_test/
```

## 핵심 감사 질문

```text
1. holdout false negative가 어디에 몰리는가
2. manufacturer 2 / SH false positive는 왜 생기는가
3. 중요 feature가 실제 holdout 일반화에 도움이 되는가
4. calibration과 threshold override가 과연 필요한가
5. drift feature를 빼면 holdout이 좋아지는가
```

## 현재까지의 요약

```text
1. FN은 특정 configuration group과 1-3d 구간에 몰렸다.
2. manufacturer 2 / SH는 별도 calibration 필요성이 확인됐다.
3. risk holdout 붕괴의 중심은 05가 아니라 06 supervised chain이었다.
4. 전면 재작성보다 03/04/06 연결 보강이 더 중요했다.
```

## 세부 문서

```text
PREPROCESSING/docs/06_false_negative_audit.md
PREPROCESSING/docs/06_false_negative_deep_audit.md
PREPROCESSING/docs/06_feature_importance_audit.md
PREPROCESSING/docs/06_group_calibration.md
PREPROCESSING/docs/06_drift_feature_ablation.md
PREPROCESSING/docs/06_manufacturer2_sh_fp_audit.md
```

legacy holdout failure notebook 자료:

```text
PREPROCESSING/docs/06_test/06_risk_leadtime_audit.md
PREPROCESSING/osj/06_test/06_risk_leadtime_audit.ipynb
```
