# HeatGrid Ops v0 Handoff Package

이 ZIP은 다른 Codex/Claude 에이전트에게 넘기기 위한 최소 실행 산출물입니다.
목표는 로컬 Postgres를 띄우고, v0 `input.json` 구조와 DB seed가 서로 맞는지 바로 확인하는 것입니다.

## 먼저 볼 파일

1. `AGENT_BRIEF.md`
2. `input.json`
3. `db/schema.sql`
4. `db/seed.sql`
5. `queries/verify.sql`

## 빠른 실행

PowerShell:

```powershell
.\scripts\verify.ps1
```

Git Bash 또는 Linux/macOS:

```bash
bash ./scripts/verify.sh
```

수동 실행:

```bash
docker compose up -d
docker compose exec -T postgres psql -U heatgrid -d heatgrid_ops < queries/verify.sql
```

기본 접속 정보:

```text
host: 127.0.0.1
port: 55432
database: heatgrid_ops
user: heatgrid
password: heatgrid
```

55432 포트가 이미 사용 중이면:

PowerShell:

```powershell
$env:HEATGRID_PG_PORT=55433
docker compose up -d
```

Git Bash:

```bash
HEATGRID_PG_PORT=55433 docker compose up -d
```

## 기대 결과

`queries/verify.sql` 실행 시 최소한 아래가 보여야 합니다.

```text
flow1_anomaly_current_best = 10
flow2_m1_specialist = 13
priority_score = 89.73322568799986
priority_level = urgent
current_best_weight = 0.65
m1_specialist_weight = 0.35
```

`input.json`의 핵심 구조:

```text
raw_context.window
raw_context.current_best_sensor_values.values      # current-best raw sensor aggregate top N, v0 N=10
raw_context.m1_specialist_features.features        # M1 specialist compact13, exactly 13
priority_context.priority
priority_context.priority.calculation
priority_context.model_signals
priority_context.explanation.review_required
priority_context.explanation.review_reasons
```

`priority_context.formula`, root `priority_context.review_reasons`, `priority_context.card.review_required`는 사용하지 않습니다.

## 정리

컨테이너와 볼륨까지 지우려면:

```bash
docker compose down -v
```
