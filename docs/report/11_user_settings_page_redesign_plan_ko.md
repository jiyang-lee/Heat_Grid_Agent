# 이용자 개인 설정 페이지 통합 개편 계획

작성일: 2026-07-16
기준 브랜치: develop2
기준 HEAD: `e7c01d6` 기능(개발환경): 팀 공용 실행 환경 구성
작업 브랜치: `feat/ai-activity-ui` (로컬 전용, push 없음)

## 개요

현재 `SettingsPage.tsx`는 운영/관리자 성격이 섞인 3개 탭(화면 및 환경 / 알림 설정 / 업무 설정)이고, 알림 임계값이 백엔드 자동화 정책 API(`useAutomationPolicy`/`useUpdateAutomationPolicy`)에 저장된다. 이를 **로그인한 이용자 본인에게만 적용되는 개인 설정 페이지**로 개편한다. 관리자 전용 운영 정책·시스템 설정은 제외하고, 개인화 항목만 3개 탭(내 프로필 / 화면 및 알림 / 로그인 및 보안)으로 재구성한다.

## 절대 준수 원칙

1. 로컬 작업만 (push 없음)
2. 백엔드 수정 절대 불가 (`frontend/src/`만)
3. 정상/고장 두 시나리오 공통 반영
4. 기능 없이 프론트 UI만 (백엔드 연결 없음)

- 동작 수준(확정): 컨트롤은 로컬 상태로 실제 인터랙티브, **다크모드는 기존 테마 시스템대로 실작동**, 저장·API 호출 없음.
- 두 시나리오 공통은 자동 충족: `App.tsx`에서 `page === 'settings'`는 모드 분기 없이 `SettingsPage` 하나로 렌더됨 → `App.tsx`는 건드리지 않는다.

## 수정 대상 (frontend 2파일)

| 파일 | 작업 |
| --- | --- |
| `frontend/src/console/SettingsPage.tsx` | 컴포넌트 전면 재작성 |
| `frontend/src/console/operations.css` | 신규 요소 CSS를 `.settings-*` 네임스페이스로만 추가 |

공유 `.activity-tabs`·`.toast-success`·공용 `ui.tsx`·`useThemePreference` 훅은 수정 없이 재사용한다.

## SettingsPage.tsx 재작성 내용

### 공통 프레임
- 콘텐츠 상단에 `.page-title` 헤더 추가(다른 페이지 패턴 재사용, `AiActivityPage.tsx`):
  - 제목 `설정` / 설명 `나에게 적용되는 화면, 알림 및 계정 환경을 관리합니다.`
- 탭 바는 기존 `.activity-tabs` role=tablist 재사용, 탭 배열을 `['내 프로필', '화면 및 알림', '로그인 및 보안']`로 교체 (기존 3개 탭명은 코드·화면에서 완전 제거)
- 우측 액션: `기본값 복원`(로컬 상태 리셋) / `변경 사항 저장`(성공 토스트만, 백엔드 호출 없음)
- 백엔드 훅 제거: `useAutomationPolicy`·`useUpdateAutomationPolicy` import·호출·"현재 적용 정책" aside 삭제 / `theme` prop은 유지
- 레이아웃은 기존 `.settings-layout`(main + aside 2열) 재사용, aside는 "내 계정 요약"(이름/역할/소속/마지막 로그인, 순수 표시)으로 대체

### 탭 1 — 내 프로필
- 프로필 카드: 아바타(`users` 아이콘/이니셜), 이름·역할·소속, "사진 변경" 버튼(UI만)
- 개인 기본 정보 폼(`.form-grid`, 로컬 state controlled input): 이름 / 사번(ID) / 이메일 / 연락처 / 부서·소속 / 직무

### 탭 2 — 화면 및 알림 (기존 화면 및 환경 + 알림 설정 + 업무 설정의 개인화 항목 통합)
- 화면 표시(`.form-grid`): 화면 모드(시스템/라이트/다크 라디오 → `themePreference`/`onThemePreferenceChange` 실작동) / 언어 / 시간대 / 온도·압력·유량 단위
- 기본 시작 화면 & 목록 표시 선호(기존 업무 설정에서 개인화 항목 이관): 기본 시작 화면(홈/알림/AI 조치) / 실행 현황 정렬 / 자동 새로고침 주기 / 페이지당 표시 개수
- 알림 수신 채널(`.channel-grid` + `.switch` 재사용, 로컬 state): 푸시 / 이메일 / 문자 / 메신저
- **제외**: 기존 "알림 임계값"(운영 정책 API 저장 = 관리자 영역)은 삭제

### 탭 3 — 로그인 및 보안
- 비밀번호 변경 폼(현재/신규/확인, UI만 — 제출 시 유효성 안내 토스트, 백엔드 없음)
- 2단계 인증(2FA) 토글(`.switch`) + 안내 문구
- 활성 세션/현재 기기 표시(순수 표시)
- 접속 기록: 최근 로그인 목록(더미 데이터, `.history-list` 재사용) — 일시 / 기기·브라우저 / IP / 위치

## 재사용 자산 (신규 코드 최소화)

- 컴포넌트: `SurfaceCard`·`Button`·`StatusBadge` (`console/ui.tsx`), `Icon` (`console/icons.tsx` — users/shield/bell/settings/clock/check 등 보유)
- 테마: `useThemePreference`가 주는 `preference`/`setPreference` prop (App.tsx가 이미 전달, 훅 자체는 미수정)
- CSS: `.page-title`·`.activity-tabs`·`.settings-layout`·`.settings-form`·`.settings-aside`·`.settings-summary`·`.form-grid`·`.check-label`·`.switch`·`.channel-grid`·`.toast-success` (기존 정의 재사용)
- 신규 CSS: 프로필 카드·접속 기록·비밀번호 폼 등은 `.settings-profile`·`.settings-security`·`.settings-access-log` 등 설정 전용 클래스로만 추가

## 하지 않는 것

- 백엔드/`App.tsx`/`AppShell.tsx`/공유 CSS·컴포넌트/테마 훅 수정 없음, push 없음, 모드 분기 추가 없음
- 실제 저장·인증·API 연동 없음(전부 프론트 UI + 로컬 상태)

## 검증

1. `frontend`에서 dev 서버 로컬 실행(5173/5180, 백엔드 불필요)
2. EntryGate → **정상** 선택 → 설정 진입: ①탭이 내 프로필/화면 및 알림/로그인 및 보안 3개뿐 ②기존 3개 탭명 미노출 ③콘텐츠 상단 "설정 / 나에게 적용되는…" 표시 ④컨트롤 인터랙티브 ⑤다크모드 라디오 → 전 화면 실제 다크 적용
3. EntryGate로 나가 **고장** 선택 → 설정 진입: 위와 **동일**하게 표시되는지 확인(공통 반영)
4. `npm run typecheck` / `lint` / `build` 통과, 콘솔 오류 0, 반응형·가로 스크롤 없음
