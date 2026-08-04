import { useCallback, useEffect, useRef, useState } from 'react'
import { replayApi } from '../api/backend'
import type { ReplayReading } from '../api/contracts'
import { fallbackSensorPoint, hasFaultScenarioProfile, initialSensorPoints, SCENARIO_INCIDENT_AT, SCENARIO_START_AT } from './scenarioData'
import type { EntryMode, ScenarioIncidentState, SensorPoint, SensorStreamState } from './types'

const POLL_MS = 1_500
const FAULT_POLL_MS = 1_500
const FAULT_TICK_SECONDS = 0.2
const MAX_POINTS = 13

function numericValue(reading: ReplayReading, key: string): number | null {
  const value = reading.values[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function pointFromReading(reading: ReplayReading): SensorPoint | null {
  const supply = numericValue(reading, 'p_net_supply_temperature')
  const returnTemperature = numericValue(reading, 'p_net_return_temperature')
  const flow = numericValue(reading, 'p_net_meter_flow')
  if (supply == null || returnTemperature == null || flow == null || reading.simulated_at == null || reading.sequence == null) return null
  return { at: reading.simulated_at, supply, returnTemperature, flow, quality: reading.quality == null ? 'unknown' : 'validated', sequence: reading.sequence }
}

function seedState(mode: EntryMode, substationId: number, incidentState: ScenarioIncidentState, endAt?: string): SensorStreamState {
  // Reopening a saved fault session must keep its active incident visible.
  // Without this anchor it restarted at the scenario's pre-fault beginning,
  // making the already-active alert disappear until simulated time caught up.
  const seedEndAt = endAt ?? (mode === 'fault' && incidentState === 'incident-active' ? SCENARIO_INCIDENT_AT : undefined)
  const points = initialSensorPoints(mode, substationId, seedEndAt)
  const latest = points.at(-1)
  const incidentPoint = mode === 'fault' && incidentState === 'incident-active' && latest
    ? { ...fallbackSensorPoint(mode, substationId, true, 0, latest.at), at: latest.at, sequence: latest.sequence }
    : null
  return {
    status: 'connecting',
    source: 'scenario-fallback',
    points: incidentPoint ? [...points.slice(0, -1), incidentPoint] : points,
    simulatedAt: incidentPoint?.at ?? latest?.at ?? SCENARIO_START_AT,
    receivedAt: null,
    nextReceiveSeconds: 3,
    paused: false,
    speed: 1,
    substationId,
    connectionMessage: 'Replay 센서 스트림 연결 중',
  }
}

export function useSensorStream(mode: EntryMode | null, enabled: boolean, substationId: number, incidentState: ScenarioIncidentState) {
  const activeMode = mode ?? 'normal'
  const [state, setState] = useState<SensorStreamState>(() => seedState(activeMode, substationId, incidentState))
  const [resetKey, setResetKey] = useState(0)
  const pausedRef = useRef(false)
  const speedRef = useRef(1)
  const simulatedAtRef = useRef(state.simulatedAt)
  const manualRefreshRef = useRef<() => void>(() => {})
  const restartAtScenarioStartRef = useRef(false)
  const activeModeRef = useRef(activeMode)
  const incidentActiveRef = useRef(activeMode === 'fault' && incidentState === 'incident-active')

  useEffect(() => {
    pausedRef.current = state.paused
    speedRef.current = state.speed
    simulatedAtRef.current = state.simulatedAt
  }, [state.paused, state.simulatedAt, state.speed])

  useEffect(() => {
    incidentActiveRef.current = activeMode === 'fault' && incidentState === 'incident-active'
  }, [activeMode, incidentState])

  useEffect(() => {
    if (!enabled || mode == null) return undefined
    let cancelled = false
    let timer: number | undefined
    let fallbackSequence = 0
    let faultSequence = -1
    let failures = 0
    const modeChanged = activeModeRef.current !== activeMode
    const pollMs = activeMode === 'fault' ? FAULT_POLL_MS : POLL_MS
    activeModeRef.current = activeMode

    const appendPoint = (point: SensorPoint, source: SensorStreamState['source'], message: string) => {
      if (cancelled) return
      setState((current) => {
        if (current.points.at(-1)?.sequence === point.sequence && source === 'backend-replay') return current
        return {
          ...current,
          status: current.paused ? 'paused' : source === 'backend-replay' ? 'live' : 'fallback',
          source,
          points: [...current.points, point].slice(-MAX_POINTS),
          simulatedAt: point.at,
          receivedAt: new Date().toISOString(),
          nextReceiveSeconds: 3,
          connectionMessage: message,
        }
      })
    }

    const advanceFallback = (reason: string) => {
      if (pausedRef.current) return
      fallbackSequence += 1
      faultSequence = incidentActiveRef.current ? faultSequence + 1 : -1
      setState((current) => {
        const previous = current.points.at(-1)
        if (!previous) return current
        const next = fallbackSensorPoint(activeMode, substationId, incidentActiveRef.current, fallbackSequence, previous.at, faultSequence)
        return {
          ...current,
          status: 'fallback',
          source: 'scenario-fallback',
          points: [...current.points, next].slice(-MAX_POINTS),
          simulatedAt: next.at,
          receivedAt: new Date().toISOString(),
          nextReceiveSeconds: 3,
          connectionMessage: reason,
        }
      })
    }

    const startFallback = (reason: string) => {
      setState((current) => ({ ...current, status: current.paused ? 'paused' : 'fallback', source: 'scenario-fallback', connectionMessage: reason }))
      manualRefreshRef.current = () => advanceFallback(reason)
      const tick = () => {
        advanceFallback(reason)
        if (!cancelled) timer = window.setTimeout(tick, Math.max(300, pollMs / speedRef.current))
      }
      timer = window.setTimeout(tick, Math.max(300, pollMs / speedRef.current))
    }

    const connect = async () => {
      const replayStartAt = restartAtScenarioStartRef.current || modeChanged ? SCENARIO_START_AT : simulatedAtRef.current
      restartAtScenarioStartRef.current = false
      setState(seedState(activeMode, substationId, incidentActiveRef.current ? 'incident-active' : 'monitoring', replayStartAt))
      if (activeMode === 'fault' && hasFaultScenarioProfile(substationId)) {
        startFallback('동시다발 고장 시나리오 검증 데이터를 재생 중입니다.')
        return
      }
      try {
        const datasets = await replayApi.listDatasets()
        if (cancelled) return
        const scenarioTime = Date.parse(SCENARIO_START_AT)
        const matching = datasets.find((dataset) => Date.parse(dataset.replay_start) <= scenarioTime && Date.parse(dataset.replay_end) >= scenarioTime)
        const dataset = activeMode === 'fault' ? matching : datasets[0]
        if (!dataset) {
          startFallback('Replay 데이터셋이 없어 검증된 시나리오 대체 데이터를 표시합니다.')
          return
        }
        const created = await replayApi.createRun({ dataset_id: dataset.dataset_id, start_at: activeMode === 'fault' ? replayStartAt : dataset.replay_start, tick_seconds: activeMode === 'fault' ? FAULT_TICK_SECONDS : 3, requested_by: 'ops-scenario-ui' })
        if (cancelled) return
        await replayApi.command(created.run_id, { command_type: 'start', expected_run_version: created.version, payload: {}, requested_by: 'ops-scenario-ui', idempotency_key: `${created.run_id}-start` })
        if (cancelled) return
        const refreshFromBackend = () => {
          if (pausedRef.current) return
          void replayApi.snapshot(created.run_id).then((snapshot) => {
            failures = 0
            const reading = snapshot.readings.find((item) => item.substation_id === substationId)
            const point = reading ? pointFromReading(reading) : null
            if (point) appendPoint(point, 'backend-replay', '실시간 센서 연동 수신 중')
            else advanceFallback('선택 기계실 sensor_reading 수신 전까지 시나리오 대체 데이터를 표시합니다.')
          }).catch((error: unknown) => {
            failures += 1
            if (error instanceof Error && failures < 3) {
              setState((current) => ({ ...current, status: 'reconnecting', connectionMessage: '센서 스트림 재연결 중' }))
              return
            }
            if (timer != null) window.clearInterval(timer)
          startFallback('실시간 센서 연동이 중단되어 시나리오 대체 데이터로 전환했습니다.')
          })
        }
        setState((current) => ({ ...current, status: 'live', source: 'backend-replay', connectionMessage: '실시간 센서 연동 수신 중' }))
        manualRefreshRef.current = refreshFromBackend
        timer = window.setInterval(refreshFromBackend, pollMs)
      } catch (error: unknown) {
        if (error instanceof Error) {
          startFallback('실시간 센서 연동에 연결할 수 없어 시나리오 대체 데이터를 표시합니다.')
          return
        }
        throw error
      }
    }

    void connect()
    return () => {
      cancelled = true
      manualRefreshRef.current = () => {}
      if (timer != null) window.clearInterval(timer)
    }
  }, [activeMode, enabled, mode, resetKey, substationId])

  const togglePaused = useCallback(() => setState((current) => ({
    ...current,
    paused: !current.paused,
    status: current.paused ? (current.source === 'backend-replay' ? 'live' : 'fallback') : 'paused',
    connectionMessage: current.paused ? (current.source === 'backend-replay' ? '실시간 센서 연동 수신 중' : '시나리오 대체 데이터 재생 중') : '센서 재생 일시정지',
  })), [])
  const setSpeed = useCallback((speed: number) => setState((current) => ({ ...current, speed })), [])
  const reset = useCallback(() => {
    restartAtScenarioStartRef.current = true
    simulatedAtRef.current = SCENARIO_START_AT
    setState(seedState(activeMode, substationId, 'monitoring', SCENARIO_START_AT))
    setResetKey((current) => current + 1)
  }, [activeMode, substationId])
  const refresh = useCallback(() => manualRefreshRef.current(), [])

  return { state, togglePaused, setSpeed, reset, refresh }
}
