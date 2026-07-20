import { useEffect, useState } from 'react'
import { ApiError, operationsApi, replayApi } from '../api/client'
import type { CurrentUser, OperationsPolicy, ShiftSchedule } from '../api/contracts'
import { useScenario } from '../scenario/useScenario'
import { Button, StatusBadge, SurfaceCard } from './ui'

interface Props {
  readonly onModeChanged: () => void
  readonly refreshRevision: number
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return '다른 관리자가 먼저 저장했습니다. 최신 정책을 다시 불러오세요.'
  if (error instanceof ApiError && error.status === 403) return '관리자 권한이 필요합니다.'
  return error instanceof Error ? error.message : '요청을 처리하지 못했습니다.'
}

export function AdminPage({ onModeChanged, refreshRevision }: Props) {
  const scenario = useScenario()
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [policy, setPolicy] = useState<OperationsPolicy | null>(null)
  const [datasets, setDatasets] = useState(0)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setError(null)
    try {
      const [nextUser, nextPolicy, replayDatasets] = await Promise.all([
        operationsApi.currentUser(),
        operationsApi.policy(),
        replayApi.listDatasets(),
      ])
      setUser(nextUser)
      setPolicy(nextPolicy)
      setDatasets(replayDatasets.filter((item) => item.status === 'available' || item.status === 'imported').length)
    } catch (caught: unknown) {
      setError(errorMessage(caught))
    }
  }

  useEffect(() => { void load() }, [refreshRevision])

  const updateShift = (index: number, patch: Partial<ShiftSchedule>) => {
    setPolicy((current) => {
      if (current == null) return current
      const shifts = current.shifts.map((shift, shiftIndex) => shiftIndex === index ? { ...shift, ...patch } : shift) as unknown as OperationsPolicy['shifts']
      return { ...current, shifts }
    })
  }

  const savePolicy = async () => {
    if (policy == null) return
    setBusy(true)
    setError(null)
    try {
      setPolicy(await operationsApi.updatePolicy({
        expected_version: policy.version,
        timezone: policy.timezone,
        freshness_threshold_minutes: policy.freshness_threshold_minutes,
        anomaly_confirmations: policy.anomaly_confirmations,
        recovery_confirmations: policy.recovery_confirmations,
        shifts: policy.shifts,
      }))
      setNotice('운영 정책을 저장했습니다.')
    } catch (caught: unknown) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  const enterReplay = () => {
    if (datasets === 0) {
      setError('사용 가능한 재생 데이터셋이 없습니다.')
      return
    }
    scenario.startFaultScenario()
    onModeChanged()
  }

  const returnToNormal = () => {
    scenario.selectMode('normal')
    onModeChanged()
  }

  return <div className="page-stack admin-page">
    <div className="admin-summary-grid">
      <SurfaceCard title="현재 운영자"><div className="admin-summary"><strong>{user?.display_name ?? '운영자'}</strong><span>{user?.auth_mode === 'fixed' ? '고정 운영자 권한' : '사용자 정보 확인 중'}</span><StatusBadge tone={user?.capabilities.includes('admin') ? 'success' : 'neutral'}>{user?.capabilities.includes('admin') ? '관리 가능' : '확인 중'}</StatusBadge></div></SurfaceCard>
      <SurfaceCard title="훈련·시뮬레이션"><div className="admin-summary"><strong>{datasets}개 데이터셋</strong><span>훈련 화면은 관리자에서만 시작하고 종료합니다.</span>{scenario.state.mode === 'fault' ? <Button onClick={returnToNormal}>정상 운영으로 복귀</Button> : <Button disabled={datasets === 0} onClick={enterReplay} tone="primary">재생 훈련 시작</Button>}</div></SurfaceCard>
    </div>
    <SurfaceCard title="운영 판정 정책">
      {policy == null ? <p className="admin-empty">정책을 불러오는 중입니다.</p> : <div className="admin-policy-grid">
        <label><span>데이터 지연 기준</span><input min="1" onChange={(event) => setPolicy({ ...policy, freshness_threshold_minutes: Number(event.target.value) })} type="number" value={policy.freshness_threshold_minutes} /><small>분</small></label>
        <label><span>anomaly 생성 연속 횟수</span><input min="1" onChange={(event) => setPolicy({ ...policy, anomaly_confirmations: Number(event.target.value) })} type="number" value={policy.anomaly_confirmations} /><small>회</small></label>
        <label><span>정상 해소 연속 횟수</span><input min="1" onChange={(event) => setPolicy({ ...policy, recovery_confirmations: Number(event.target.value) })} type="number" value={policy.recovery_confirmations} /><small>회</small></label>
        {policy.shifts.map((shift, index) => <fieldset key={shift.shift_id}><legend>{index === 0 ? '주간 교대' : '야간 교대'}</legend><label><span>표시 이름</span><input onChange={(event) => updateShift(index, { label: event.target.value })} value={shift.label} /></label><label><span>시작</span><input onChange={(event) => updateShift(index, { start_time: event.target.value })} type="time" value={shift.start_time} /></label><label><span>종료</span><input onChange={(event) => updateShift(index, { end_time: event.target.value })} type="time" value={shift.end_time} /></label></fieldset>)}
        <div className="admin-policy-actions"><span>정책 버전 v{policy.version} · {policy.timezone}</span><Button disabled={busy} onClick={() => void savePolicy()} tone="primary">{busy ? '저장 중' : '정책 저장'}</Button></div>
      </div>}
      {error && <p className="form-error">{error} <button onClick={() => void load()} type="button">다시 불러오기</button></p>}
      {notice && <p className="form-success">{notice}</p>}
    </SurfaceCard>
  </div>
}
