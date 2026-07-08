# DB 입력 기준

v2는 seed 파일을 직접 포함하지 않고 PostgreSQL의 기존 운영 카드 테이블을 읽는다.

필수 테이블:

```text
priority_cards
priority_decisions
windows
substations
priority_card_review_reasons
sensor_summaries
```

기본 연결 문자열:

```text
postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops
```

다른 DB를 사용할 때:

```powershell
$env:HEATGRID_DATABASE_URL="postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB"
uv run python 05_시뮬레이션/versions/v2_postgres_react_ops/backend/server.py
```
