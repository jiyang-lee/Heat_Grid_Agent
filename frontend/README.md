# HeatGrid Agent — Frontend (React + Vite, 최소 대시보드)

우선순위 표 → 상세(근거 센서) → 보고서/메일 초안 검토 화면.

## 실행
```bash
# 1) 백엔드(FastAPI) 먼저 기동 (리포 루트에서)
uv run uvicorn server.main:app --port 8000

# 2) 프론트
cd frontend
npm install
npm run dev   # http://localhost:5173 (/priority, /agent 는 8000으로 프록시)
```

## 데이터 흐름
- `GET /priority?limit=50` → 표
- 행 클릭 → `GET /priority/{key}` (상세) + `GET /agent/output/{key}` (보고서/메일 md)

> 참고: 본 자율 실행 환경에서는 네트워크 의존 `npm install` 을 수행하지 않았다(소스만 제공).
> 한 사이클 end-to-end 검증은 백엔드 엔드포인트(curl)로 완료했다.
