# 이용자 개인 설정 페이지 개편 완료 보고

작성일: 2026-07-16
기준 브랜치: develop2
기준 HEAD: `e7c01d6` 기능(개발환경): 팀 공용 실행 환경 구성
결과 커밋: `f54e880` feat(settings): 이용자 개인 설정 페이지 3탭 개편 — **develop2에 push 완료** (`e7c01d6..f54e880`)

## 개요

운영/관리자 성격이 섞여 있던 설정 화면(화면 및 환경 / 알림 설정 / 업무 설정)을, **로그인한 본인에게만 적용되는 개인 설정 3탭**(내 프로필 / 화면 및 알림 / 로그인 및 보안)으로 전면 재구성했다. 관리자 전용 운영 정책·시스템 설정(알림 임계값 등 자동화 정책 API 저장 항목)은 이용자 설정 화면에서 제외했다. 계획 문서는 `docs/report/11_user_settings_page_redesign_plan_ko.md` 참조.

작업 원칙(사용자 지정 4대 원칙):

1. 로컬 작업만 — 작업 중 push 금지 (*완료 시점에 사용자 지시로 해제하고 develop2에 push*)
2. 백엔드 수정 절대 불가 — `frontend/src/`만 수정
3. 정상·고장 두 시나리오 공통 반영
4. 기능 없이 프론트 UI만 — 백엔드 연결·저장 없음

3번은 구조적으로 자동 충족된다: `App.tsx`에서 `page === 'settings'`는 모드 분기 없이 `SettingsPage` 하나로 렌더되므로, 정상/고장 어느 모드로 진입해도 동일한 화면이 나온다(양 모드 렌더 실측 확인).

## 변경 파일

| 영역 | 파일 | 역할 |
| --- | --- | --- |
| 프론트 화면 | `console/SettingsPage.tsx` | 3탭 전면 재작성. 백엔드 훅(`useAutomationPolicy`/`useUpdateAutomationPolicy`) 제거, 전 컨트롤 로컬 상태화 |
| 프론트 CSS | `console/operations.css` | 설정 전용 `.profile-*`·`.sn-*`·`.sec-*` 스타일 + 설정 페이지 글자 크기 스케일 블록 추가 |
| 프론트 아이콘 | `console/icons.tsx` | 9종 additive 추가 — `lock`·`mail`·`phone`·`idcard`·`monitor`·`sun`·`moon`·`grid`·`list` |
| 문서 | `docs/report/11_user_settings_page_redesign_plan_ko.md` | 개편 계획 |

**커밋하지 않은 로컬 변경**

| 파일 | 사유 |
| --- | --- |
| `frontend/src/main.tsx` | develop2 버그(#1) 우회용 **로컬 전용** 수정(미설치 devtools import 비활성화). 코드 주석에 "커밋/push 금지, 조원 upstream 정리 대상" 명시 |
| `frontend/.env.local` | `VITE_USE_MOCK=true` (gitignore 대상) |
| `scenario/scenario.css` | 작업 중 2회 수정했으나 **서로 상쇄되어 원본과 동일**(아래 "해결한 문제" 참조) → 커밋 대상 없음 |

## 탭별 구현

세 탭 모두 **풀폭 패널 + 하단 액션 바(취소 / 변경사항 저장)** 로 통일했다. 그 결과 기존 우측 사이드(내 계정 요약·저장 범위)와 상단 전역 버튼(기본값 복원 등)은 제거됐다.

### 내 프로필

- **좌측 프로필 카드**: 아바타 · 이름(홍길동) · `운영자` 뱃지 · 소속(지역난방 운영팀) · `● 활성 사용자` · 구분선 · 사번(HG-1024) / 연락처 / 이메일 아이콘 목록
- **우측 폼** — 기본 정보: 이름(🔒 잠금) · 연락처(편집) · 이메일(🔒 잠금) · 직책(select) · 소속(select) / 개인 환경: 언어 · 기본 연락 방식
- 좌:우 = **3:7**, 카드↔폼 간격 **1cm(37.8px)**, 라벨 열 132px(`nowrap`)

### 화면 및 알림

- **화면 모드**: 시스템 설정 따름 / 라이트 모드 / 다크 모드 — 아이콘 카드 3개. `useThemePreference`와 연결되어 **다크모드만 실제로 동작**
- **화면 표시 옵션**: 시간 형식 · 날짜 형식 · 컴팩트 간격 사용 · 애니메이션 효과 · 툴팁 표시 · 글꼴 크기
- **기본 시작 화면**: 홈 / 알림 / AI 활동
- **알림 수신 설정**: 알림 채널(브라우저·이메일·SMS) · 알림음 · 방해 금지 시간(22:00–07:00) · 방해 금지 중 긴급 알림 허용 · 미확인 알림 재알림 주기 · 알림 미리보기 표시
- **목록 표시 선호**(하단 전체 폭): 테이블 보기 / 카드 보기 라디오 카드

### 로그인 및 보안

- **보안 설정**: 비밀번호 변경 `[변경]` · 2단계 인증 · 새 기기 로그인 알림 · 로그인 유지 시간
- **현재 로그인 기기**(표): 기기명 / 위치 / 최근 접속 / 상태 — `현재 사용 중`(파랑) · `활성`(초록) 배지
- **최근 로그인 기록**(표): 기기명 / 위치 / 일시 / IP 주소 (4행)
- **보안 작업**(빨간 경고 박스): `다른 모든 기기에서 로그아웃` / `활동 기록 다운로드`

## 재사용 자산

- 컴포넌트: `SurfaceCard`·`Button`(tone primary/ghost/danger)·`StatusBadge`·`Icon` — 수정 없이 재사용
- 테마: `useThemePreference`의 `preference`/`setPreference` prop (훅 자체 미수정)
- 기존 CSS: `.activity-tabs`·`.switch`·`.toast-success`·`.ops-surface`·`.status-badge` 등

## 해결한 문제 (비직관적 이슈)

1. **설정 골격 CSS는 `operations.css`가 아니라 `scenario/scenario.css`에 있다.** `.settings-page`·`.settings-layout`·`.settings-tabbar`·`.settings-actions`가 거기 정의돼 있고, `App.tsx` 로드 순서가 operations → scenario라 **scenario가 나중에 로드되어 덮어쓴다**. operations.css만 grep하면 안 보여 중복 규칙을 추가하기 쉬움 → 두 파일 모두 확인 필요.
2. **거대 공백 버그**: `.settings-page`는 원래 2행 그리드(`auto minmax(0,1fr)`, 자식=탭바+레이아웃 전제)였다. 요청대로 제목 헤더를 추가해 자식이 3개가 되자 **탭바가 늘어나는 `1fr` 행을 차지해 370px로 부풀고** `align-items:end` 때문에 내용이 바닥에 붙었다. → 3행(`auto auto minmax(0,1fr)`)으로 수정해 해결. 이후 사용자가 제목 헤더 제거를 요청해 **2행으로 되돌림** → 최종적으로 scenario.css는 원본과 동일.
3. **다크모드 입력 배경**: 다크 입력 배경은 `scenario.css:243`의 셀렉터 목록이 관할한다. 신규 입력 클래스는 목록에 없어 다크에서 흰 배경이 되므로, `:root[data-theme='dark'] .profile-field-control input …` 같은 규칙을 operations.css에 직접 추가했다.
4. **탭 글자가 작던 이유**: `.activity-tabs button`에 `font-size`가 없어 **버튼의 UA 기본값(13.33px)** 을 쓰고 있었다(폰트 상속 안 받음). 글자 크기 스케일 블록에서 명시적으로 14px 지정.

## 세부 조정 이력 (사용자 피드백 반영)

| 항목 | 최종 |
| --- | --- |
| 카드 : 폼 비율 | 4:6 → **3:7** |
| 카드↔폼 간격 | **1cm(37.8px)** (`gap: var(--space-4) 1cm`) |
| 라벨 열 | 100 → **132px** + `nowrap` (「기본 연락 방식」 한 줄 정렬) |
| 입력 칸 | 620px 캡 → **`1fr`(폼 열 채움)** — "화면을 채워달라" 요청 반영 |
| 프로필 카드 높이 | **min-height 670px** = 화면 및 알림 카드 높이와 일치, 하단 버튼은 flex로 바닥 고정 |
| 개인 환경 | 시간 형식·날짜 형식 삭제(화면 및 알림 탭에 존치) → 언어·기본 연락 방식만 |
| 프로필 카드 메타 순서 | 사번 → **연락처 → 이메일** |
| 페이지 제목 | 「설정 / 나에게 적용되는…」 헤더 **제거** |
| 글자 크기 | 설정 화면 전반 **+0.5pt(≈0.67px)** — 탭 13.33→14px 포함 |

글자 크기는 `operations.css`의 **"설정 페이지 글자 크기 스케일"** 블록 한 곳에서 관리한다. 추후 조정은 이 블록만 수정하면 된다.

## 검증

원칙 4번에 따라 **실백엔드 없이 mock 모드**(`VITE_USE_MOCK=true`)로 dev 서버만 띄워 검증했다.

- 3탭 구조·문구·컨트롤 렌더 및 인터랙션 실측(DOM 계측 + 스크린샷): 탭 전환, 양방향 바인딩(연락처 입력 → 좌측 카드 실시간 반영), 취소 시 기본값 복원, 토글/select 동작, 위험 버튼 토스트
- **화면 모드 다크 라디오 → 전 화면 실제 다크 적용** 확인(`data-theme=dark`, 입력·표·경고 박스 배경 정상)
- **정상·고장 두 모드에서 동일 렌더** 확인(그리드·탭·구조 실측 일치)
- 레이아웃: 1536/1800px에서 가로 스크롤 0, 라벨 줄바꿈 없음
- 정적 검사: `oxlint` 무경고(exit 0), 브라우저 콘솔 오류 0

> `npm run build`(tsc)는 **develop2 기존 버그**(#2 contracts 중복 선언, #3 mockApi export 누락)로 실패한다. 이번 작업 코드와 무관하며, dev 서버(esbuild)는 타입 오류를 무시하므로 검증에 지장 없음.

## 알려진 이슈 · 후속 과제

**develop2 자체 버그** (별도 리포트로 조원 공유 완료, 이번 작업과 무관)

| # | 파일 | 증상 |
| --- | --- | --- |
| 1 | `main.tsx` | 미설치 `react-grab`/`react-scan` 정적 import → dev 서버 500(백지). **현재 로컬에서만 우회 중 — 미커밋** |
| 2 | `api/contracts.ts` | 타입 26개 중복 선언 → `tsc` 실패 |
| 3 | `api/mockApi.ts` | export 6개 누락 → `backend.ts`에서 `mock.alertsApi`가 undefined → **mock 정상 모드에서 알림·AI 활동 데이터가 0/빈 상태**(고장 모드는 시나리오 데이터라 정상) |
| 4 | `scenario/ScenarioReportWorkspace.tsx` | 없는 속성 `changeNote` 사용(→`changeSummary`) |
| 5 | `console/ai-activity/ExecutionDetail.tsx` | `review.data.result` 잘못된 접근 + 영어 라벨 잔존 |

**이번 작업에서 남긴 것**

- `.settings-profile-card`의 `min-height: 670px`는 화면 및 알림 카드 높이에 맞춘 **고정값**이다. 해당 탭 내용이 바뀌어 높이가 달라지면 같이 조정해야 한다.
- 개편으로 미사용이 된 CSS가 남아 있다(`.settings-form`·`.channel-grid`·`.settings-aside`·`.settings-summary`·`.settings-access-log`·`.access-*`·`.settings-theme-row`·`.check-label` 등). 동작에는 영향 없으나 정리 여지 있음.
- 원칙 4번에 따라 **실제 저장·인증·API 연동은 없다.** 저장/취소는 토스트만 표시하고, 접속 기록·기기 목록은 더미 데이터다. 백엔드 연동 시 이 부분을 실 API로 교체해야 한다.
