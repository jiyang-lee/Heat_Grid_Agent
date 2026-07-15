import { useMemo, useState } from 'react'
import {
  useAlerts,
  useDemoReplayControl,
  useDemoReplayPresets,
  useDemoReplaySnapshot,
  useDemoReplayStatus,
  useDemoReplayStream,
  useHealth,
  usePrioritySnapshot,
} from '../api/hooks'
import type {
  DemoReplayControlAction,
  DemoReplayPreset,
  DemoReplayState,
  PriorityEvaluationResult,
  ReplaySensorDefinition,
  ReplaySensorReading,
} from '../api/contracts'
import { Icon } from './icons'
import { ApiState, MetricCard, Sparkline, StatusBadge, SurfaceCard, type Tone } from './ui'

interface DashboardTableRow {
  manufacturerId: string
  substationId: number
  priority: PriorityEvaluationResult | null
  reading: ReplaySensorReading | null
}

function priorityTone(value: string | null): Tone {
  if (value == null) return 'neutral'
  if (value === 'urgent') return 'critical'
  if (value === 'high') return 'warning'
  if (value === 'medium') return 'notice'
  return 'success'
}

function sensorValue(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '미수집'
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 }).format(value)
}

function simulatedTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  }).format(date)
}

function replayLabel(state: DemoReplayState | undefined): string {
  if (state === 'running') return '가상 실시간 재생 중'
  if (state === 'paused') return '가상 재생 일시정지'
  if (state === 'completed') return '가상 재생 완료'
  if (state === 'error') return '가상 재생 오류'
  if (state === 'disabled') return '가상 재생 비활성'
  return '가상 재생 준비'
}

function replayControl(
  state: DemoReplayState | undefined,
  simulatedAt: string | null | undefined,
): { action: DemoReplayControlAction; label: string } | null {
  if (state === 'running') return { action: 'pause', label: '일시정지' }
  if (state === 'paused') {
    return simulatedAt
      ? { action: 'resume', label: '계속 재생' }
      : { action: 'start', label: '재생 시작' }
  }
  if (state === 'completed') return null
  if (state === 'ready') return { action: 'start', label: '재생 시작' }
  return null
}

function sortedSensors(sensors: ReplaySensorDefinition[]): ReplaySensorDefinition[] {
  return [...sensors].sort(
    (left, right) =>
      left.display_order - right.display_order || left.sensor_key.localeCompare(right.sensor_key),
  )
}

function presetLabel(preset: DemoReplayPreset): string {
  const level = preset.label === 'pre_fault_demo' ? 'HIGH' : 'MEDIUM'
  return `${level} · H ${preset.fleet_high_count} / M ${preset.fleet_medium_count} · ${simulatedTime(preset.event_at)}`
}

export function DashboardPage() {
  const priority = usePrioritySnapshot()
  const alerts = useAlerts({ status: 'open' })
  const health = useHealth()
  const replayStatus = useDemoReplayStatus()
  const replaySnapshot = useDemoReplaySnapshot()
  const replayMutation = useDemoReplayControl()
  const replayPresets = useDemoReplayPresets()
  const [seekValue, setSeekValue] = useState('2023-01-08T00:00')
  const [presetId, setPresetId] = useState('')
  useDemoReplayStream()

  const rawPriorityRows = useMemo(() => priority.data?.results ?? [], [priority.data?.results])
  const sensorReadings = useMemo(
    () => replaySnapshot.data?.readings ?? [],
    [replaySnapshot.data?.readings],
  )
  const replay = replayStatus.data ?? replaySnapshot.data
  const awaitingFirstScore = replay
    ? replay.state !== 'disabled' && !replay.has_scored_window
    : replayStatus.isLoading || replaySnapshot.isLoading
  const priorityRows = awaitingFirstScore ? [] : rawPriorityRows
  const sensors = useMemo(
    () => sortedSensors(replaySnapshot.data?.sensors ?? replayStatus.data?.sensors ?? []),
    [replaySnapshot.data?.sensors, replayStatus.data?.sensors],
  )
  const rows = useMemo<DashboardTableRow[]>(() => {
    const bySubstation = new Map<number, DashboardTableRow>()

    for (const reading of sensorReadings) {
      bySubstation.set(reading.substation_id, {
        manufacturerId: reading.manufacturer_id,
        substationId: reading.substation_id,
        priority: null,
        reading,
      })
    }
    for (const result of rawPriorityRows) {
      const existing = bySubstation.get(result.substation_id)
      bySubstation.set(result.substation_id, {
        manufacturerId: result.manufacturer_id,
        substationId: result.substation_id,
        priority: awaitingFirstScore ? null : result,
        reading: existing?.reading ?? null,
      })
    }

    return [...bySubstation.values()].sort((left, right) => left.substationId - right.substationId)
  }, [awaitingFirstScore, rawPriorityRows, sensorReadings])

  const hotCount = priorityRows.filter(
    (row) => row.priority_level === 'urgent' || row.priority_level === 'high',
  ).length
  const averageRisk =
    priorityRows.length === 0
      ? 0
      : priorityRows.reduce((sum, row) => sum + (row.risk_score ?? 0), 0) /
        priorityRows.length
  const trend = useMemo(() => [1.8, 2.1, 2.4, 2.0, 2.7, 2.4, 2.5], [])
  const openAlerts = awaitingFirstScore ? [] : (alerts.data ?? [])
  const control = replayControl(replay?.state, replay?.current_simulated_at)
  const beforeFirstScore =
    replay != null && replay.state !== 'disabled' && !replay.has_scored_window

  return (
    <div className="page-stack">
      <header className="page-title">
        <div>
          <h1>지역난방 운영 보조 대시보드</h1>
          <p>운영 데이터와 우선순위 모델을 함께 확인합니다.</p>
        </div>
        <div className="replay-header-controls">
          <label className="replay-preset">
            <span>발표 프리셋</span>
            <select
              aria-label="발표 프리셋"
              disabled={replayPresets.isLoading || !replayPresets.data?.length}
              onChange={(event) => {
                const nextId = event.target.value
                const preset = replayPresets.data?.find((item) => item.scenario_id === nextId)
                setPresetId(nextId)
                if (preset) setSeekValue(preset.seek_at.slice(0, 16))
              }}
              value={presetId}
            >
              <option value="">검증 구간 선택</option>
              {replayPresets.data?.map((preset) => (
                <option key={preset.scenario_id} value={preset.scenario_id}>
                  {presetLabel(preset)}
                </option>
              ))}
            </select>
          </label>
          <label className="replay-seek">
            <span>가상 시각 이동</span>
            <input
              aria-label="이동할 가상 시각"
              max="2026-01-07T23:50"
              min="2023-01-08T00:00"
              onChange={(event) => setSeekValue(event.target.value)}
              step={600}
              type="datetime-local"
              value={seekValue}
            />
          </label>
          <button
            className="ops-button replay-icon-button"
            disabled={
              replayMutation.isPending || !replay || !seekValue || replay.state === 'disabled'
            }
            onClick={() =>
              replayMutation.mutate({
                action: 'seek',
                simulated_at: `${seekValue}:00+09:00`,
              })
            }
            title="선택한 가상 시각으로 이동"
            type="button"
          >
            <Icon name="calendar" /> 이동
          </button>
          {control && (
            <button
              className="ops-button"
              disabled={replayMutation.isPending}
              onClick={() => replayMutation.mutate({ action: control.action })}
              type="button"
            >
              {control.label}
            </button>
          )}
          <button
            className="ops-button"
            disabled={replayMutation.isPending || !replay || replay.state === 'disabled'}
            onClick={() => replayMutation.mutate({ action: 'reset' })}
            type="button"
          >
            초기화
          </button>
          <span
            className={`live-indicator replay-state-${replay?.state ?? 'ready'}`}
            title={replay?.error ?? undefined}
          >
            <i />
            {replayLabel(replay?.state)}
          </span>
        </div>
      </header>
      <div className="metric-grid metric-grid-five">
        <MetricCard
          icon="building"
          label="총 관리 건물 수"
          value={String(rows.length || 31)}
          hint="운영 대상 전체"
        />
        <MetricCard
          icon="alert"
          label="긴급 알림 수"
          value={String(hotCount)}
          hint="즉시 검토 필요"
          tone="critical"
        />
        <MetricCard
          icon="calendar"
          label="오늘 점검 필요"
          value={String(openAlerts.length)}
          hint="예정 포함"
          tone="warning"
        />
        <MetricCard
          icon="shield"
          label="평균 위험도"
          value={`${(averageRisk * 5).toFixed(1)} / 5.0`}
          hint="활성 평가 기준"
          tone="critical"
        />
        <MetricCard
          icon="check"
          label="정상 설비 비율"
          value={
            priorityRows.length ? `${Math.max(0, 100 - hotCount * 3).toFixed(1)}%` : '-'
          }
          hint="최근 스냅샷 기준"
          tone="success"
        />
      </div>
      <div className="dashboard-grid">
        <div className="dashboard-left">
          <SurfaceCard className="ai-trend-card" title="AI 운영 요약">
            <div className="ai-summary">
              <div>
                <p className="summary-callout">
                  현재 {hotCount || 0}개 기계실이 높은 위험 상태입니다.
                </p>
                <p>
                  우선순위 평가 결과를 기준으로 경보 대상과 권장 조치를 정렬했습니다. 실제
                  알림과 상세 근거는 알림 메뉴에서 검토할 수 있습니다.
                </p>
                <button className="text-link" type="button">
                  상세 현황 보기 <Icon name="arrow" />
                </button>
              </div>
              <div className="trend-block">
                <div className="trend-heading">
                  <strong>위험도 추이</strong>
                  <span>최근 7일</span>
                </div>
                <svg
                  aria-label="최근 7일 위험도 추이"
                  className="large-trend"
                  viewBox="0 0 300 150"
                >
                  <path className="large-grid" d="M0 25H300M0 62H300M0 99H300M0 136H300" />
                  <polyline
                    points={trend
                      .map((value, index) => `${index * 50},${136 - value * 30}`)
                      .join(' ')}
                  />
                  <polyline
                    className="trend-secondary"
                    points="0,113 50,98 100,98 150,44 200,81 250,81 300,98"
                  />
                </svg>
                <div className="trend-axis">
                  <span>07/05</span>
                  <span>07/07</span>
                  <span>07/09</span>
                  <span>07/11</span>
                </div>
              </div>
            </div>
          </SurfaceCard>
          <SurfaceCard
            action={
              <div className="sensor-table-actions">
                <span className="synthetic-chip">가상 데이터</span>
                <span className="count-chip">전체 {rows.length}</span>
              </div>
            }
            title="기계실/건물 상태 현황"
          >
            {beforeFirstScore && (
              <div className="window-progress" role="status">
                <span>6시간 데이터 수집 중</span>
                <strong>{Math.min(36, Math.max(0, replay.window_progress))} / 36</strong>
                <progress max={36} value={Math.min(36, Math.max(0, replay.window_progress))} />
              </div>
            )}
            <ApiState
              empty={rows.length === 0}
              error={priority.isError && replaySnapshot.isError}
              loading={priority.isLoading && replaySnapshot.isLoading}
              retry={() => {
                void priority.refetch()
                void replaySnapshot.refetch()
              }}
            />
            {rows.length > 0 && (
              <div className="table-scroll sensor-table-scroll">
                <table className="ops-table sensor-table">
                  <thead>
                    <tr>
                      <th>기계실/건물명</th>
                      {sensors.map((sensor) => (
                        <th key={sensor.sensor_key}>
                          <span>{sensor.label_ko}</span>
                          {sensor.unit && <small>{sensor.unit}</small>}
                        </th>
                      ))}
                      <th>우선순위</th>
                      <th>상태</th>
                      <th>가상 시각</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={`${row.manufacturerId}-${row.substationId}`}>
                        <td>
                          <strong>
                            {row.manufacturerId} #{row.substationId}
                          </strong>
                          <small>기계실 {row.substationId}</small>
                        </td>
                        {sensors.map((sensor) => {
                          const value = row.reading?.values[sensor.sensor_key]
                          const quality = row.reading?.quality[sensor.sensor_key]
                          return (
                            <td key={sensor.sensor_key}>
                              <span
                                className={`sensor-reading${value == null ? ' sensor-missing' : ''}`}
                                title={quality ? `데이터 상태: ${quality}` : undefined}
                              >
                                {sensorValue(value)}
                              </span>
                            </td>
                          )
                        })}
                        <td>
                          <span className="risk-value">
                            {row.priority?.risk_score == null
                              ? '-'
                              : ((row.priority.risk_score ?? 0) * 5).toFixed(1)}
                          </span>
                        </td>
                        <td>
                          <StatusBadge tone={priorityTone(row.priority?.priority_level ?? null)}>
                            {row.priority?.priority_level ?? '평가 대기'}
                          </StatusBadge>
                        </td>
                        <td>{simulatedTime(row.reading?.simulated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SurfaceCard>
        </div>
        <div className="dashboard-center">
          <SurfaceCard title="수도권 설비 현황">
            <div className="mock-map" aria-label="수도권 설비 분포 모형">
              <div className="map-title">서울특별시</div>
              {rows.slice(0, 14).map((row, index) => (
                <button
                  aria-label={`${row.manufacturerId} ${row.substationId}`}
                  className={`map-marker tone-${priorityTone(row.priority?.priority_level ?? null)}`}
                  key={`${row.manufacturerId}-${row.substationId}`}
                  style={{
                    left: `${14 + ((index * 19) % 74)}%`,
                    top: `${18 + ((index * 29) % 64)}%`,
                  }}
                  type="button"
                />
              ))}
              <div className="map-note">
                API 좌표 계약이 없어 운영 위치는 모형으로 표시합니다.
              </div>
            </div>
          </SurfaceCard>
          <SurfaceCard title="AI 추천 조치">
            <ol className="recommendation-list">
              {openAlerts.slice(0, 4).map((alert, index) => (
                <li key={alert.alert_id}>
                  <b>{index + 1}</b>
                  <div>
                    <strong>
                      {alert.manufacturer_id} #{alert.substation_id} 현장 상태 확인
                    </strong>
                    <span>{alert.enqueue_reason}</span>
                  </div>
                  <StatusBadge
                    tone={alert.priority_level === 'urgent' ? 'critical' : 'warning'}
                  >
                    {alert.priority_level === 'urgent' ? '긴급' : '권장'}
                  </StatusBadge>
                </li>
              ))}
              {openAlerts.length === 0 && (
                <li>
                  <b>1</b>
                  <div>
                    <strong>활성 알림이 없습니다.</strong>
                    <span>백엔드 연결 상태를 확인해 주세요.</span>
                  </div>
                </li>
              )}
            </ol>
          </SurfaceCard>
        </div>
        <div className="dashboard-right">
          <SurfaceCard
            action={
              <button className="text-link" type="button">
                전체 보기
              </button>
            }
            title="주요 알림"
          >
            <ApiState
              empty={openAlerts.length === 0}
              error={alerts.isError}
              loading={alerts.isLoading}
              retry={() => void alerts.refetch()}
            />
            {openAlerts.slice(0, 5).map((alert) => (
              <div className="compact-alert" key={alert.alert_id}>
                <span
                  className={`alert-symbol tone-${
                    alert.priority_level === 'urgent' ? 'critical' : 'warning'
                  }`}
                >
                  <Icon name="alert" />
                </span>
                <div>
                  <strong>{alert.enqueue_reason}</strong>
                  <span>
                    {alert.manufacturer_id} #{alert.substation_id}
                  </span>
                </div>
                <StatusBadge
                  tone={alert.priority_level === 'urgent' ? 'critical' : 'warning'}
                >
                  {alert.priority_level === 'urgent' ? '심각' : '경고'}
                </StatusBadge>
              </div>
            ))}
          </SurfaceCard>
          <SurfaceCard title="예상 조치 시점">
            <div className="lead-grid">
              <article>
                <span>누수 점검 완료 예상</span>
                <strong>2시간 내</strong>
                <Icon name="clock" />
              </article>
              <article>
                <span>압력 안정화 예상</span>
                <strong>4시간 내</strong>
                <Icon name="clock" />
              </article>
              <article>
                <span>센서 교체 예정</span>
                <strong>당일 내</strong>
                <Icon name="calendar" />
              </article>
              <article>
                <span>열교환기 점검 완료</span>
                <strong>2일 내</strong>
                <Icon name="calendar" />
              </article>
            </div>
          </SurfaceCard>
          <SurfaceCard title="연결 상태">
            <div className="connection-list">
              <p>
                <span>백엔드 API</span>
                <StatusBadge tone={health.data?.database === 'connected' ? 'success' : 'neutral'}>
                  {health.data?.database ?? '확인 중'}
                </StatusBadge>
              </p>
              <p>
                <span>모델 서비스</span>
                <StatusBadge tone={health.data?.openai === 'configured' ? 'success' : 'neutral'}>
                  {health.data?.openai ?? '확인 중'}
                </StatusBadge>
              </p>
              <Sparkline tone="primary" values={[4, 5, 4, 6, 7, 5, 6]} />
            </div>
          </SurfaceCard>
        </div>
      </div>
    </div>
  )
}
