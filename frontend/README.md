# HeatGrid 운영 대시보드 (frontend)

세종 1생활권 지역난방 31개 단지 운영 대시보드. React 19 + Vite + TypeScript.
화면: **지도 관제**(MapLibre 3D) · **기계실 관제**(설비 이미지 배치) · **운영 콘솔**(알림/에이전트).

## 빠른 시작

```bash
cd frontend
npm install
cp .env.example .env      # 아래 값 채우기
npm run dev               # → http://localhost:5173
```

> `.env`는 커밋되지 않습니다(비밀값). 클론/풀 직후 **반드시 직접 만들어야** 합니다. 안 만들면 지도 관제에 지도가 안 뜨고, 운영 콘솔이 백엔드 호출에 실패합니다. (기계실 관제 화면은 로컬 데이터라 `.env` 없이도 표시됩니다.)

## .env 설정

`.env.example`을 복사한 뒤 채웁니다.

| 변수 | 설명 |
|---|---|
| `VITE_MAP_STYLE_URL` | MapTiler 키 또는 전체 style JSON URL. **비워두면 지도 안 뜸.** 키는 레포에 커밋하지 말고 팀 채널에서 공유받거나 각자 [MapTiler](https://cloud.maptiler.com/)에서 발급. |
| `VITE_USE_MOCK` | `true`면 백엔드 없이 mock 데이터로 전체 화면 구동(데모 권장). 미설정/`false`면 실백엔드(`VITE_BACKEND_URL`) 호출. |
| `VITE_BACKEND_URL` | 실백엔드 프록시 대상. 기본 `http://127.0.0.1:8003`. |

**백엔드 없이 전체 화면을 보려면** `.env`에 다음 두 줄이면 충분합니다:

```bash
VITE_MAP_STYLE_URL=<MapTiler 키>
VITE_USE_MOCK=true
```

MapTiler 키는 브라우저에 노출되는 클라이언트 키입니다 → MapTiler 대시보드에서 **Allowed origins** 제한을 거는 것을 권장합니다.

## 스크립트

| 명령 | 설명 |
|---|---|
| `npm run dev` | 개발 서버(HMR) |
| `npm run build` | 타입체크 + 프로덕션 빌드 |
| `npm run typecheck` | 타입만 검사(`tsc -b --noEmit`) |
| `npm run lint` | Oxlint |
| `npm run preview` | 빌드 산출물 미리보기 |

## 참고

- API 계약/타입: `src/api/contracts.ts` (백엔드 `schemas.py`와 1:1). mock/real 스위치는 `src/api/backend.ts`.
- 기계실 설비 이미지: `src/assets/machines/*.png`, 매핑은 `src/room/machineArt.ts`. 배포 전 리사이즈/WebP 최적화 여지 있음.

---

<details>
<summary>Vite 템플릿 참고</summary>

React + TypeScript + Vite (Oxlint) 기반. 타입 인지 린트를 켜려면 `oxlint-tsgolint` 설치 후 `.oxlintrc.json`에 `"options": { "typeAware": true }`를 추가한다. [Oxlint rules](https://oxc.rs/docs/guide/usage/linter/rules) · [React Compiler](https://react.dev/learn/react-compiler/installation).

</details>
