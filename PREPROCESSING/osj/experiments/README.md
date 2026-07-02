# Experiments

이 폴더는 공식 파이프라인에서 제외된 실험/감사/ablation 코드를 보관한다.

공식 실행 순서에는 포함하지 않는다.
모델 개선 근거를 재검토하거나 성능 저하 원인을 다시 볼 때만 사용한다.

## 폴더 구성

- `06_test/`: 개별 06 실험/감사 스크립트와 과거 노트북
- `06_risk_experiments.py`: risk 실험 묶음 실행 wrapper
- `06_leadtime_experiments.py`: leadtime 실험 묶음 실행 wrapper
- `06_risk_audit.py`: false negative, feature importance, drift audit 묶음 실행 wrapper

## 실행 예

```powershell
python PREPROCESSING/osj/experiments/06_risk_experiments.py --list
python PREPROCESSING/osj/experiments/06_risk_experiments.py --run thermal
python PREPROCESSING/osj/experiments/06_risk_audit.py --run false_negative
```

주의: 이 폴더의 결과는 공식 전달 모델 패키지에 자동 포함하지 않는다.
