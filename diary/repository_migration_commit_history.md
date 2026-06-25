# Repository Migration Commit History

이 문서는 GitHub 리포지토리를 다른 리포로 옮길 때, 기존 커밋 히스토리를 문서로 보존하기 위해 작성했다.

새 리포에서 Git commit history가 유지되지 않더라도, 아래 기록을 통해 기존 작업 흐름과 주요 변경 단위를 확인할 수 있다.

## 기준 정보

- 기존 브랜치: `mlmodel`
- 기존 원격: `https://github.com/jiyang-lee/HeatGrid_Agent.git`
- 기록 기준 시점: 2026-06-25
- 기록 범위: 현재 `mlmodel` 브랜치의 전체 커밋
- 주의: 이 문서는 커밋 히스토리 요약이다. 실제 Git 객체와 diff를 완전히 대체하지는 않는다.

## 전체 작업 흐름 요약

1. 초기 프로젝트 생성
2. Python/Jupyter 실행 환경 구성
3. PreDist raw data 다운로드/정리 노트북 추가
4. ML handoff, output contract, paper guideline 문서 작성
5. 00~05 전처리/라벨 정렬/윈도우/feature selection/Isolation Forest 흐름 정리
6. 06 risk 및 leadtime 모델링 체인 추가
7. 06 실험/감사/성능 검토 문서화
8. 레거시 및 테스트 산출물 아카이브
9. 07 Priority Engine 추가
10. Agent/DB handoff용 데이터 계약 정리
11. 전처리 입력 컬럼, 인코딩 컬럼, one-hot 결과 컬럼 계약 보강

## 커밋 타임라인

| 순서 | 커밋 | 날짜 | 메시지 | 주요 내용 |
|---:|---|---|---|---|
| 1 | `205f420` | 2026-06-23 09:43 | `first commit` | 초기 `README.md` 추가 |
| 2 | `48b0def` | 2026-06-23 11:33 | `chore: 파이썬 버전 고정` | `.python-version` 추가 |
| 3 | `072f42f` | 2026-06-23 11:33 | `chore: 초기 실행 엔트리포인트 추가` | `main.py` 추가 |
| 4 | `032f4a1` | 2026-06-23 11:33 | `fix: raw_data와 다운로드 캐시를 Git 추적에서 제외` | `.gitignore` 추가 |
| 5 | `1f2da4b` | 2026-06-23 11:33 | `feat: 주피터 노트북 실행 의존성 추가` | `pyproject.toml` 추가 |
| 6 | `7d4397e` | 2026-06-23 11:33 | `chore: 주피터 실행 의존성 잠금 파일 갱신` | `uv.lock` 추가 |
| 7 | `75527b0` | 2026-06-23 11:33 | `feat: 데이터 다운로드 및 정리용 전처리 노트북 추가` | `PREPROCESSING/docs/00_load_dataset.md` 추가 |
| 8 | `c362d25` | 2026-06-23 11:34 | `feat: 데이터 다운로드 및 정리용 전처리 노트북 추가` | `PREPROCESSING/00_load_dataset.ipynb` 추가 |
| 9 | `f6f3482` | 2026-06-23 12:27 | `docs: ML 인수 문서와 산출물 계약 정리` | `ML_AGENT_HANDOFF_SPEC.md`, `ML_HANDOFF.md`, `ML_OUTPUT_CONTRACT.md` 추가 |
| 10 | `9651bc4` | 2026-06-23 12:27 | `docs: PreDist 기반 ML 작업 가이드라인 추가` | `ML_PAPER_GUIDELINE.md` 추가 |
| 11 | `c396a03` | 2026-06-23 12:27 | `docs: ML 노트북 진행 계획 추가` | `ML_NOTEBOOK_PLAN.md` 추가 |
| 12 | `0ab2e29` | 2026-06-25 13:07 | `chore: 프로젝트 설정 및 ignore 규칙 정리` | `.gitignore`, `pyproject.toml`, `uv.lock` 정리 |
| 13 | `de33602` | 2026-06-25 13:07 | `feat: 전처리 노트북 및 문서 추가` | 00~05 노트북/문서 추가 및 `00_load_dataset.ipynb`를 `PREPROCESSING/osj/`로 이동 |
| 14 | `ab767ce` | 2026-06-25 13:07 | `feat: risk 및 leadtime 모델링 파이프라인 추가` | 06 risk/leadtime 공식 스크립트와 결정 문서 추가 |
| 15 | `c7541e3` | 2026-06-25 13:08 | `docs: risk 및 leadtime 실험 감사 문서 추가` | 06 feature, drift, false negative, weighting, leadtime 실험/감사 문서 추가 |
| 16 | `9b61ae7` | 2026-06-25 13:08 | `chore: 레거시 및 테스트 전처리 산출물 아카이브` | `PREPROCESSING/legacy/`, `PREPROCESSING/osj/06_test/`, `PREPROCESSING/docs/06_test/` 정리 |
| 17 | `f0df241` | 2026-06-25 13:08 | `feat: priority engine 파이프라인 추가` | 07 priority engine 노트북, 스크립트, 분석 문서 추가 |
| 18 | `067a5fc` | 2026-06-25 13:08 | `docs: agent 데이터 계약 문서 추가` | Agent/DB handoff용 데이터 계약 문서 및 JSON 추가 |
| 19 | `1b3d5e0` | 2026-06-25 13:08 | `docs: ML handoff 및 프로젝트 진행 기록 정리` | ML handoff 문서, 요청 문서, diary 기록 추가 |
| 20 | `c94d9df` | 2026-06-25 13:19 | `docs: 데이터 계약의 형식 변환 및 인코딩 컬럼 구분 추가` | 데이터 계약에 형식 변환/인코딩 후 컬럼 구분 추가 |
| 21 | `193970f` | 2026-06-25 13:57 | `docs: 전처리와 feature engineering 컬럼 기준 분리` | 전처리 산출물과 feature engineering 결과 컬럼의 개념 분리 |
| 22 | `76d57cc` | 2026-06-25 14:00 | `docs: 전처리 입력 컬럼 계약 문서 추가` | feature engineering 이전 입력 컬럼 계약 문서 추가 |
| 23 | `6f78f7a` | 2026-06-25 14:06 | `docs: 전처리 입력 계약에 원핫 컬럼 매핑 추가` | raw/control 및 context one-hot 결과 컬럼 매핑 추가 |

## 단계별 상세 기록

### 1. 초기 프로젝트 및 실행 환경

관련 커밋:

- `205f420` `first commit`
- `48b0def` `chore: 파이썬 버전 고정`
- `072f42f` `chore: 초기 실행 엔트리포인트 추가`
- `032f4a1` `fix: raw_data와 다운로드 캐시를 Git 추적에서 제외`
- `1f2da4b` `feat: 주피터 노트북 실행 의존성 추가`
- `7d4397e` `chore: 주피터 실행 의존성 잠금 파일 갱신`

주요 내용:

- README, Python 버전, 기본 실행 엔트리포인트 구성
- raw data와 다운로드 캐시를 Git 추적에서 제외
- Jupyter 기반 전처리/ML 작업을 위한 의존성 구성

### 2. 초기 데이터 로드 및 ML 문서 기반

관련 커밋:

- `75527b0` `feat: 데이터 다운로드 및 정리용 전처리 노트북 추가`
- `c362d25` `feat: 데이터 다운로드 및 정리용 전처리 노트북 추가`
- `f6f3482` `docs: ML 인수 문서와 산출물 계약 정리`
- `9651bc4` `docs: PreDist 기반 ML 작업 가이드라인 추가`
- `c396a03` `docs: ML 노트북 진행 계획 추가`

주요 내용:

- `00_load_dataset` 문서 및 노트북 추가
- ML handoff, output contract, paper guideline, notebook plan 문서 추가
- 이후 PreDist 기반 ML 파이프라인의 문서 기준 마련

### 3. 00~05 전처리 및 Isolation Forest 흐름

관련 커밋:

- `0ab2e29` `chore: 프로젝트 설정 및 ignore 규칙 정리`
- `de33602` `feat: 전처리 노트북 및 문서 추가`

주요 내용:

- `PREPROCESSING/osj/00_load_dataset.ipynb`
- `PREPROCESSING/osj/01_raw_inspection.ipynb`
- `PREPROCESSING/osj/02_label_alignment.ipynb`
- `PREPROCESSING/osj/03_preprocess_windows.ipynb`
- `PREPROCESSING/osj/04_feature_selection.ipynb`
- `PREPROCESSING/osj/05_baseline_anomaly_model.ipynb`
- 각 단계별 대응 문서 `00`~`05` 추가

단계 의미:

- 01: raw 데이터 구조 확인
- 02: fault/disturbance/normal event 라벨 정렬
- 03: windowing 및 feature 생성 기반 마련
- 04: 모델 입력 feature selection
- 05: Isolation Forest 기반 anomaly score 생성

### 4. 06 risk 및 leadtime 모델링

관련 커밋:

- `ab767ce` `feat: risk 및 leadtime 모델링 파이프라인 추가`
- `c7541e3` `docs: risk 및 leadtime 실험 감사 문서 추가`

주요 내용:

- LightGBM risk 모델 체인 추가
- pseudo leadtime bucket 모델 체인 추가
- group calibration, promotion decision, official model 문서 추가
- risk/leadtime 성능 감사 및 실험 문서 추가

중요한 방향:

- Isolation Forest는 정상 패턴 대비 이상징후 탐지
- LightGBM risk는 고장신고 전 위험 패턴 유사도 판단
- leadtime은 실제 고장 발생 시점 예측이 아니라 신고 기준 pseudo leadtime bucket 판단

### 5. 레거시 및 실험 파일 아카이브

관련 커밋:

- `9b61ae7` `chore: 레거시 및 테스트 전처리 산출물 아카이브`

주요 내용:

- 기존 paper-aligned legacy 흐름을 `PREPROCESSING/legacy/`로 이동
- 06 실험 파일을 `PREPROCESSING/osj/06_test/` 및 `PREPROCESSING/docs/06_test/`로 분리
- 공식 파이프라인과 실험/레거시 자산을 구분

### 6. 07 Priority Engine

관련 커밋:

- `f0df241` `feat: priority engine 파이프라인 추가`

주요 내용:

- `PREPROCESSING/osj/07_priority_engine.ipynb`
- `PREPROCESSING/osj/07_priority_engine.py`
- `PREPROCESSING/osj/07_priority_engine_tuned.py`
- `PREPROCESSING/docs/07_priority_engine.md`
- `PREPROCESSING/docs/07_priority_engine_analysis.md`

Priority Engine 입력 방향:

- anomaly score
- risk score/probability/level
- leadtime bucket/confidence/probability
- recent fault/task event history

Priority Engine 출력 방향:

- `priority_score`
- `priority_level`
- component score
- priority reason

### 7. Agent/DB 데이터 계약

관련 커밋:

- `067a5fc` `docs: agent 데이터 계약 문서 추가`
- `c94d9df` `docs: 데이터 계약의 형식 변환 및 인코딩 컬럼 구분 추가`
- `193970f` `docs: 전처리와 feature engineering 컬럼 기준 분리`
- `76d57cc` `docs: 전처리 입력 컬럼 계약 문서 추가`
- `6f78f7a` `docs: 전처리 입력 계약에 원핫 컬럼 매핑 추가`

주요 문서:

- `PREPROCESSING/docs/agent_feature_contract.md`
- `PREPROCESSING/docs/agent_full_data_contract.md`
- `PREPROCESSING/docs/agent_required_raw_columns.md`
- `PREPROCESSING/docs/agent_preprocessed_input_columns.md`

주요 JSON:

- `data/processed/ml_features/agent_feature_contract.json`
- `data/processed/ml_features/agent_full_data_contract.json`
- `data/processed/ml_features/agent_required_raw_columns.json`

정리된 핵심 기준:

- operational raw 전체 후보는 의미상 50개
- 일부 raw 파일에는 `outdoor_temperature` 중복 헤더가 있어 pandas 기준 literal header union은 51개로 보일 수 있음
- 전처리 후 유지되는 operational base columns는 29개
- 형식 변환 후 의미가 그대로 유지되는 base columns는 18개
- 인코딩 대상 raw/control columns는 11개
- source metadata는 `manufacturer`, `substation_id`, `source_file`
- context source는 `configuration_types.csv`, `faults.csv`, `disturbances.csv`, `normal_events.csv`

### 8. Handoff 및 diary

관련 커밋:

- `1b3d5e0` `docs: ML handoff 및 프로젝트 진행 기록 정리`

주요 내용:

- ML handoff 문서 갱신
- ML output contract 갱신
- ML notebook plan 갱신
- `ml_request_simple.md` 추가
- diary 기록 추가

주요 diary:

- `diary/2026-06-23_ml_preprocessing_diary.md`
- `diary/2026-06-24_ml_04_05_diary.md`
- `diary/2026-06-24_ml_06_audit_diary.md`
- `diary/2026-06-24_ml_06_diary.md`
- `diary/2026-06-24_ml_06_resume_handoff.md`
- `diary/total_input.md`

## 새 리포로 이전할 때 권장 방식

히스토리까지 그대로 보존하고 싶으면 새 리포가 비어 있을 때 아래 방식이 가장 좋다.

```powershell
git remote rename origin old-origin
git remote add origin https://github.com/새계정/새리포.git
git push -u origin mlmodel
```

새 리포에 이미 커밋이 있어서 히스토리를 그대로 유지하기 어렵다면, 최소한 이 문서를 같이 포함해 이전 작업 흐름을 보존한다.

추가로 완전한 Git 객체 백업이 필요하면 아래처럼 bundle을 만들 수 있다.

```powershell
git bundle create heatgrid_mlmodel_history.bundle --all
```

나중에 bundle에서 복원하려면:

```powershell
git clone heatgrid_mlmodel_history.bundle restored_repo
```

## 현재 기준 최종 상태

현재 `mlmodel` 브랜치의 최신 주요 커밋은 다음이다.

```text
6f78f7a docs: 전처리 입력 계약에 원핫 컬럼 매핑 추가
76d57cc docs: 전처리 입력 컬럼 계약 문서 추가
193970f docs: 전처리와 feature engineering 컬럼 기준 분리
c94d9df docs: 데이터 계약의 형식 변환 및 인코딩 컬럼 구분 추가
1b3d5e0 docs: ML handoff 및 프로젝트 진행 기록 정리
067a5fc docs: agent 데이터 계약 문서 추가
f0df241 feat: priority engine 파이프라인 추가
9b61ae7 chore: 레거시 및 테스트 전처리 산출물 아카이브
c7541e3 docs: risk 및 leadtime 실험 감사 문서 추가
ab767ce feat: risk 및 leadtime 모델링 파이프라인 추가
de33602 feat: 전처리 노트북 및 문서 추가
0ab2e29 chore: 프로젝트 설정 및 ignore 규칙 정리
```
