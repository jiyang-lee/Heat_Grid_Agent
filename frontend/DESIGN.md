# HeatGrid Operations Console Design System

## 0. Research Log

- User references: 5 supplied HeatOps console captures (dashboard, alerts, reports, settings, administration) define the reference-fidelity contract.
- Existing product: extracted the real API boundary from `src/api/contracts.ts` and existing TanStack Query hooks; existing dark map shell is replaced only at the app surface.
- Skipped: external design research and generated concepts; the supplied high-resolution references are the authoritative visual input.

## 1. Atmosphere & Identity

신뢰감 있는 밝은 운영 콘솔이다. 흰 표면과 넓은 여백으로 수치가 먼저 읽히고, 파랑은 조작 가능한 경로에만, 위험 색은 상태와 우선순위에만 사용한다. 시그니처는 `좌측 작업 맥락 + 넓은 운영 표면 + 필요한 순간에만 열리는 우측 상세`의 3단 작업 흐름이다.

## 2. Color

| Role | Token | Value | Usage |
|---|---|---|---|
| Canvas | `--ops-canvas` | `#f7f8fa` | App background |
| Surface | `--ops-surface` | `#ffffff` | Cards, panels |
| Surface muted | `--ops-surface-muted` | `#f8fafc` | Table header, inset |
| Text primary | `--ops-text` | `#172033` | Headings, values |
| Text secondary | `--ops-text-muted` | `#64748b` | Metadata |
| Border | `--ops-border` | `#e4eaf2` | Separators |
| Primary | `--ops-primary` | `#1677ea` | Primary action, focus |
| Primary soft | `--ops-primary-soft` | `#ecf4fd` | Selection |
| Critical | `--ops-critical` | `#ff3b30` | Severe state |
| Warning | `--ops-warning` | `#ff7a00` | Warning state |
| Notice | `--ops-notice` | `#f5b400` | Notice state |
| Success | `--ops-success` | `#16a34a` | Confirmed state |
| Critical soft | `--ops-critical-soft` | `#fff1ef` | Critical sensor and document inset |
| Warning soft | `--ops-warning-soft` | `#fff6e8` | High-priority sensor and document inset |
| Sensor return | `--ops-sensor-return` | `#2563eb` | Return-temperature series |
| Sensor flow | `--ops-sensor-flow` | `#0f9f6e` | Flow series |

Rules: status colors never become a large background; every interactive blue has a visible focus ring; no raw non-token color is used outside this file.

## 3. Typography

- Primary: `Pretendard, "Noto Sans KR", "Segoe UI", sans-serif`.
- Page title: 24px / 700 / 1.25.
- Section title: 16px / 700 / 1.4.
- Metric: 28px / 700 / 1.1.
- Body: 14px / 400 / 1.5.
- Caption: 12px / 500 / 1.4.

## 4. Spacing & Layout

Base unit: 4px. Use `--space-1` through `--space-8` (4–32px). Desktop uses a 224px sidebar, 72px topbar, 16px page gutter, and 12-column fluid content grid. Breakpoints: 1280px compact sidebar, 960px stacked details, 720px drawer-style navigation and scrollable tables.

## 5. Components

### AppShell
- Structure: sidebar, topbar, page main.
- States: selected nav, compact navigation, mobile drawer.
- Accessibility: `nav` landmark, active view uses `aria-current`.

### SurfaceCard and StatCard
- Structure: semantic `section` / `article`, title, optional action, content.
- States: default, loading skeleton, empty, error.
- Spacing: `--space-4` to `--space-6`.

### StatusBadge and IconButton
- Variants: critical, warning, notice, success, neutral; primary, ghost, danger.
- States: hover, active, focus-visible, disabled.
- Accessibility: labels are present for icon-only controls.

### DataTable and DetailPane
- States: loading, empty, API error, selected row.
- Accessibility: rows are buttons only when selectable; keyboard focus remains visible.

### Sparkline
- Structure: labelled SVG polyline and tooltip text.
- Motion: a new point fades in only; reduced motion disables it.

### EntryGate and ScenarioCard
- Structure: full-page version selector, mode cards, scenario cards, persistent safety note.
- States: default, hover, focus-visible, active scenario, disabled/upcoming scenario.
- Accessibility: every selectable card is a button; upcoming scenarios expose `aria-disabled` and remain non-interactive.

### ScenarioWorkspace and ScenarioToast

- Structure: fixed viewport shell; a page never scrolls the document. Long lists, documents and mobile work areas scroll inside their own bordered surface.
- States: monitoring before an incident, incident-active, selected alert, analysis running, action-ready toast, report draft, report issued.
- Priority language: use `urgent` and `high`; never show A/B grades in the scenario UI.
- Motion: only the affected live sensor may pulse to signal an active incident. Reduced-motion users receive a static high-contrast outline and explicit status text.
- Accessibility: toast is polite `role=status`, does not steal focus, and exposes both dismiss and navigation actions.

### SensorStream and ReviewChat
- Sensor states: connecting, live, reconnecting, paused, offline fallback; source is always visible.
- Chat states: empty guidance, operator/assistant/system messages, proposal confirmation, rerun progress, evaluation required.
- Safety: simulated or fallback data is explicitly labelled and never presented as live field telemetry.

### WorkOrderVersionRail

- Structure: narrow, content-sized version rail with selected version, revision status and the review conversation that produced each revision.
- Behavior: version selection changes the central document only; review history stays visible and uses compact operator, AI-review and execution-result rows.
- Input: Enter submits a review; Shift+Enter inserts a line break; IME composition is never submitted early.

## 6. Motion & Interaction

100–150ms ease-out for controls and 200ms ease-in-out for panels. Use only `transform` and `opacity`. Every non-essential transition is disabled by `prefers-reduced-motion`.

## 7. Depth & Surface

Strategy: mixed, but restrained. Surfaces use a 1px border plus `0 1px 2px rgba(15, 23, 42, .03)`; panels do not stack heavy shadows.

## 8. Accessibility Constraints & Accepted Debt

- WCAG 2.2 AA target: 4.5:1 text contrast, keyboard navigation, visible focus, 44px minimum touch target for primary controls, reduced motion support.
- Accepted debt: geographical map is a deterministic visual mock because no map/coordinates endpoint is exposed by the current API. It is labelled as a simulated overview and does not convey a live safety decision.
