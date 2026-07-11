# 인수인계 (HANDOFF) — 프론트 운영 대시보드 + develop2 통합

대상: 다음 작업자. 브랜치 `example/HG_f_b_1` → `develop2` PR과 함께 전달.

> **develop2-loop 통합 메모:** 아래 내용은 프론트 브랜치가 병합되기 전 작성된 기록이다. 현재 통합본은 Priority 평가 스냅샷을 지도·목록·알림·에이전트의 정본으로 유지한다. 충돌 15개는 루프 구현을 기준으로 해결했고, 비스트리밍 LLM 토큰 기록, 기계실 배치, LAN 바인딩과 Vercel SPA 설정을 선별 반영했다. 알림 단지명은 `AlertSummary.substation_id`로 해석하므로 `/cards`, 알림 기반 `ModelProvider`, 관리비 fallback은 사용하지 않는다. 로컬 백엔드 기본 포트는 `8003`이다.

---

## 0. 병합 상태 (먼저 읽기)
- **이 PR (`example/HG_f_b_1` → `develop2`) = 충돌 0, fast-forward.** develop2가 이 브랜치의 조상이라 그대로 붙는다.
- **⚠️ 조원 브랜치 `develop2-loop`(재귀 에이전트 + Priority 평가 통합)를 develop2에 합칠 때 = 15개 파일 충돌.** 이건 **이 PR과 별개**이며 다음 작업자가 해결해야 한다. (이번 작업에서 develop2-loop는 건드리지 않았다.)
  - 프론트 13: `frontend/.env.example`, `src/App.tsx`, `api/backend.ts`, `api/client.ts`, `api/hooks.ts`, `components/Header.tsx`, `components/PriorityAside.tsx`, `domain/model.ts`, `map/MapView.tsx`, `map/footprints.ts`, `map/mapConfig.ts`, `ops/AlertDetail.tsx`, `ops/AlertFeed.tsx`
  - 백엔드 2: `src/heatgrid_ops/agent/nodes.py`, `agent/services.py` (이 브랜치 변경은 +1/+9줄로 작음)
  - 해결 방침: **프론트 = 양쪽 합집합**(이 브랜치 UI/UX + 조원 통합; 이 브랜치가 이미 `ModelProvider`/`useBuildingName` 보유), **백엔드 = 조원 agent 재작업 기준 + 이 브랜치 토큰 사용량 기록 재적용.** 조원의 신규 백엔드 파일(assessment/priority evaluation/approval/tests)은 충돌 없이 수용.

---

## 1. 지금까지 진행된 것 (Done)
**프론트 운영 대시보드** (React 19 + Vite + TS, `frontend/`)
- **지도 관제**: MapLibre 3D + MapTiler 다크 타일, 마우스 회전/기울기(우클릭 드래그·나침반). 단지 위치=실측 위경도, 색=단지 tier.
- **수리 우선순위**: 비정상 단지 정렬(긴급수→주의수→관리비단가).
- **기계실 관제**: 설비 이미지 7종(`src/assets/machines/*.png`)을 스테이지 폭 전반 배치(`machines.ts` ax/ay/scale), 상태(정상/주의/긴급)·센서 미탑재(회색) 반영, 클릭↔상세 동기화.
- **운영 콘솔**: 알림 큐(자동 첫 알림 선택·자동 에이전트 실행), 토큰·비용 지표 박스 **분리(상단 고정)**, 작업지시서 카드 **하단 고정 표시**, 산출물/진행 타임라인 제거.

**데이터 연동**
- `ModelProvider`: `GET /api/alerts`(open) + `GET /cards`(card_id→substation_id)로 **단지 tier** 산출(urgent→긴급, high→주의). 건물명 enrichment=`useBuildingName`.
- **mock↔real 스위치** = `VITE_USE_MOCK`(`.env`). mock이면 백엔드 없이 전체 화면 동작(단지 tier는 관리비 단가 대리지표).

**인프라/설정**
- 지도 키 `.env`의 `VITE_MAP_STYLE_URL`(gitignore). LAN 공유(`vite.config` `server.host`). Vercel 배포 설정(`vercel.json`) + README 가이드. dev proxy 대상 8002. 에이전트 토큰 사용량 기록 수정. MapTiler 예시 키 스크럽(레포에 실제 키 없음).

## 2. 해야 할 것 (TODO)
1. **[최우선] `develop2-loop` 병합** — §0의 15개 충돌 해결.
2. 기계실 "어느 설비 고장"은 **합성값**(`domain/model.ts` `stById`, 단지 tier를 대표 설비에 배정) → 백엔드가 설비단위 신호를 주면 그 부분만 교체.
3. 지도 3D 건물 도형은 **합성 프록시**(`map/footprints.ts`, 정사각형+세대수 비례 높이) → 실 GIS 확보 시 교체.
4. 설비 이미지 리사이즈/WebP 최적화(배포 전, 현재 ~6MB).
5. 공개 배포 시 백엔드 공개 호스팅 + `/api` 연결(또는 mock 모드).

## 3. 실행 / 환경
**프론트**
```bash
cd frontend
npm install
cp .env.example .env     # VITE_MAP_STYLE_URL=<MapTiler 키>, VITE_USE_MOCK=true(백엔드 없이) / false(실백엔드)
npm run dev              # http://localhost:5173
```
**백엔드(실데이터용)**
```bash
uv run python simulator/versions/v2_postgres_react_ops/backend/server.py   # 127.0.0.1:8002
```
- 전제: PostgreSQL(도커 컨테이너 `heatgrid-pgvector`, :55432)이 떠 있어야 함. 실행 창은 계속 열어둘 것(닫으면 8002 종료).
- 확인: `http://127.0.0.1:8002/health` → `database: connected`.

## 4. 데이터 출처 요약
- 🟢 실데이터: 알림 큐/단지 tier/작업지시서/토큰(백엔드 ML priority_score + LLM).
- 🔵 정적 실측: 단지 위경도·이름·주소·센서 구성(`data/complexes.ts`, 세종 매핑).
- 🟡 합성(데모): 지도 건물 3D 도형, 기계실 개별 설비 지목.
