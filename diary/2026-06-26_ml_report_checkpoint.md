# 2026-06-26 ML report checkpoint

## 현재 기준 상태

보고서 노트북 생성과 osj 공식 실행 흐름 정리까지 완료한 상태를 롤백 기준점으로 고정했다.

현재 기준 커밋:

```text
db3ea08 docs: ML 보고서 노트북 추가
```

현재 기준 태그:

```text
checkpoint-2026-06-26-ml-report-baseline
```

원격 브랜치:

```text
origin/mlmodel1
```

원격 저장소:

```text
https://github.com/jiyang-lee/Heat_Grid_Agent.git
```

## 이 기준점에 포함된 내용

### 1. osj 공식 실행 흐름 정리

커밋:

```text
30d2308 chore: osj 공식 실행 흐름 정리
```

주요 내용:

- `PREPROCESSING/osj`를 공식 실행 노트북 중심으로 정리
- 공식 실행 흐름:

```text
00_load_dataset.ipynb
01_raw_inspection.ipynb
02_label_alignment.ipynb
03_preprocess_windows.ipynb
04_feature_selection.ipynb
05_baseline_anomaly_model.ipynb
06_risk_leadtime_models.ipynb
07_priority_engine.ipynb
08_model_handoff.ipynb
```

- 공식 실행 스크립트는 `PREPROCESSING/osj/pipeline_scripts/`로 이동
- 실험/검토 파일은 `PREPROCESSING/osj/experiments/`로 이동
- 과거 wrapper/basic 파일은 `PREPROCESSING/osj/archive/`로 이동
- 문서 내 구 경로 참조도 새 구조로 수정

### 2. ML 보고서 노트북 추가

커밋:

```text
db3ea08 docs: ML 보고서 노트북 추가
```

생성 파일:

```text
report/heatgrid_ml_project_report.ipynb
```

보고서 내용:

- 전체 ML 흐름 Sankey chart
- 29 / 195 / 189 / 221 feature 수 비교
- Isolation Forest 성능 및 threshold sweep
- Risk 모델 공식본/후보 성능 비교
- event context / thermal / combined 실험 비교
- feature importance family 분석
- Leadtime 기본/승격/버킷 재설계 비교
- Priority Engine v1/v2 분포 비교
- 공식 채택 / 보류 / 파기 판단 표
- 한국어 markdown 설명
- Plotly 기반 한국어 차트와 한국어 표

검증 결과:

```text
code cells executed: 12
plotly outputs: 29
errors: []
```

## 현재 프로젝트 해석 기준

현재 ML 구조는 아래 흐름을 기준으로 유지한다.

```text
03/04 전처리 + feature set 고정
-> 05 Isolation Forest 비지도 이상탐지
-> anomaly_score 산출
-> 06 LightGBM risk 모델
-> 06 LightGBM leadtime 3버킷 추정 모델
-> 07 Priority Engine
-> Agent 전달
```

중요한 기준:

- 29개 raw operational base column은 전처리 후 유지 기준이다.
- 195개 feature는 04 feature selection 이후 baseline feature contract다.
- 195개는 계속 고정 기준으로 둔다.
- Risk 공식 모델 입력은 189개다.
- Leadtime promoted 모델 입력은 221개다.
- 221개는 raw column 수가 아니라 leadtime 모델 전용 feature 수다.
- Leadtime 221개는 195개 기준에 risk/anomaly/timeflow 계열이 더해진 결과다.

## 앞으로 실험할 때 주의사항

성능 개선 실험은 195개 feature contract를 깨는 방식으로 진행하지 않는다.

권장 방식:

```text
195개 기본 feature contract 유지
+ 모델별 파생 feature 실험
+ 모델별 feature 선택/제외 ablation
+ event context / thermal relation / timeflow feature 비교
```

우선순위:

```text
1. risk false negative audit
2. drift 의심 feature 제거/축소 ablation
3. event context 상태형 재표현
4. thermal relation/group feature 보강
5. leadtime timeflow 확장
6. leadtime 2버킷 urgency 보조모델
7. Isolation Forest threshold/group threshold 재검토
8. Priority Engine ranking/weight 보정
9. pseudo label 재설계
```

## 롤백 방법

실험하다가 프로젝트가 깨졌거나 현재 기준점으로 돌아가야 할 때는 아래 태그를 사용한다.

```bash
git checkout checkpoint-2026-06-26-ml-report-baseline
```

위 명령은 태그 상태로 이동하는 것이므로 detached HEAD 상태가 된다.
단순 확인용으로는 안전하다.

현재 브랜치 자체를 기준점으로 되돌려야 할 때는 아래 명령을 쓴다.

```bash
git reset --hard checkpoint-2026-06-26-ml-report-baseline
```

주의:

- `git reset --hard`는 현재 작업 중인 변경사항을 지운다.
- 실험 결과를 보존해야 하면 먼저 새 브랜치나 커밋을 만든 뒤 실행한다.

## 원격 복구 기준

태그도 원격에 push되어 있다.

```text
checkpoint-2026-06-26-ml-report-baseline -> origin
```

따라서 다른 PC나 새 clone 환경에서도 아래 명령으로 기준점을 확인할 수 있다.

```bash
git fetch --tags
git checkout checkpoint-2026-06-26-ml-report-baseline
```

