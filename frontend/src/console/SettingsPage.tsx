import { useEffect, useState } from 'react'
import { useAutomationPolicy, useUpdateAutomationPolicy } from '../api/hooks'
import { ApiState, Button, StatusBadge, SurfaceCard } from './ui'

const tabs = ['화면 및 환경', '알림 설정', '업무 설정'] as const
type Tab = (typeof tabs)[number]
type Channel = 'email' | 'sms' | 'messenger' | 'push'

const defaultChannels: Record<Channel, boolean> = { email: true, sms: true, messenger: true, push: true }

function loadChannels(): Record<Channel, boolean> {
  const saved = window.localStorage.getItem('heatgrid:notification-channels')
  if (!saved) return defaultChannels
  try {
    return { ...defaultChannels, ...JSON.parse(saved) as Partial<Record<Channel, boolean>> }
  } catch {
    return defaultChannels
  }
}

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('화면 및 환경')
  const [channels, setChannels] = useState<Record<Channel, boolean>>(loadChannels)
  const [thresholds, setThresholds] = useState({ critical: 80, warning: 60, notice: 40 })
  const [saved, setSaved] = useState(false)
  const policy = useAutomationPolicy()
  const updatePolicy = useUpdateAutomationPolicy()
  const valid = thresholds.critical > thresholds.warning && thresholds.warning > thresholds.notice
  useEffect(() => {
    if (!saved) return undefined
    const timer = window.setTimeout(() => setSaved(false), 2400)
    return () => window.clearTimeout(timer)
  }, [saved])
  const restore = () => {
    setChannels(defaultChannels)
    setThresholds({ critical: 80, warning: 60, notice: 40 })
    window.localStorage.removeItem('heatgrid:notification-channels')
    setSaved(true)
  }
  const save = () => {
    if (!valid) return
    window.localStorage.setItem('heatgrid:notification-channels', JSON.stringify(channels))
    updatePolicy.mutate({
      updated_by: 'ops-manager',
      minimum_confidence: thresholds.critical / 100,
      minimum_approval_rate: thresholds.warning / 100,
      minimum_source_trust: thresholds.notice / 100,
    }, { onSuccess: () => setSaved(true) })
  }
  const toggle = (channel: Channel) => setChannels((current) => ({ ...current, [channel]: !current[channel] }))
  return <div className="page-stack settings-page">
    <header className="page-title"><div><h1>설정</h1><p>개인 운영 환경과 알림 수신, 업무 화면 기본 설정을 관리합니다.</p></div><div><Button onClick={restore}>기본값 복원</Button><Button disabled={!valid || updatePolicy.isPending} onClick={save} tone="primary">{updatePolicy.isPending ? '저장 중' : '변경 사항 저장'}</Button></div></header>
    <div className="activity-tabs" role="tablist">{tabs.map((item) => <button aria-selected={tab === item} className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)} role="tab" type="button">{item}</button>)}</div>
    <div className="settings-layout">
      <div className="settings-main">
        {tab === '화면 및 환경' && <SurfaceCard title="기본 환경 설정"><div className="settings-form"><section><h3>기본 시작 화면과 표시 단위</h3><div className="form-grid"><label>기본 시작 화면<select defaultValue="dashboard"><option value="dashboard">홈</option><option value="alerts">알림</option><option value="activity">AI 활동</option></select></label><label>언어<select defaultValue="ko"><option value="ko">한국어</option></select></label><label>시간대<select defaultValue="seoul"><option value="seoul">(UTC+09:00) 서울</option></select></label><label>온도 단위<select defaultValue="c"><option value="c">°C</option></select></label><label>압력 단위<select defaultValue="bar"><option value="bar">bar</option></select></label><label>유량 단위<select defaultValue="flow"><option value="flow">m³/h</option></select></label></div></section><section><h3>화면 모드</h3><div className="form-grid"><label className="check-label"><input defaultChecked type="radio" name="theme" />시스템 설정 따름</label><label className="check-label"><input type="radio" name="theme" />라이트 모드</label><label className="check-label"><input type="radio" name="theme" />다크 모드</label></div></section></div></SurfaceCard>}
        {tab === '알림 설정' && <SurfaceCard title="알림 수신 채널"><div className="settings-form"><section><h3>수신 채널</h3><div className="channel-grid">{([['push', '푸시 알림', '웹/모바일 푸시'], ['email', '이메일', 'ops-team@heatgrid.kr'], ['sms', '문자 메시지', '010-1234-5678'], ['messenger', '메신저', '#heatgrid-alerts']] as const).map(([key, label, detail]) => <article key={key}><div><strong>{label}</strong><span>{detail}</span></div><label className="switch"><input checked={channels[key]} onChange={() => toggle(key)} type="checkbox" /><i /></label></article>)}</div></section><section><h3>알림 임계값</h3><div className="threshold-grid">{([['critical', '심각 (Critical)'], ['warning', '경고 (Warning)'], ['notice', '주의 (Notice)']] as const).map(([key, label]) => <label key={key}><strong>{label}</strong><span>운영 정책 API에 저장됩니다.</span><input max="100" min="0" onChange={(event) => setThresholds((current) => ({ ...current, [key]: Number(event.target.value) }))} type="range" value={thresholds[key]} /><output>{thresholds[key]}%</output></label>)}</div>{!valid && <p className="form-error">심각 &gt; 경고 &gt; 주의 순서로 입력해야 저장할 수 있습니다.</p>}</section></div></SurfaceCard>}
        {tab === '업무 설정' && <SurfaceCard title="AI 활동과 문서 업무 설정"><div className="settings-form"><section><h3>AI 활동 기본 화면</h3><div className="form-grid"><label>기본 탭<select defaultValue="runs"><option value="runs">실행 현황</option><option value="reports">AI 보고서</option><option value="orders">작업지시서</option></select></label><label>실행 현황 정렬<select defaultValue="latest"><option value="latest">최근 실행 순</option></select></label><label>자동 새로고침<select defaultValue="minute"><option value="minute">1분</option></select></label></div></section><section><h3>문서 발행 원칙</h3><div className="form-grid"><label className="check-label"><input defaultChecked type="checkbox" />사람 승인 후 작업지시서 발행</label><label className="check-label"><input defaultChecked type="checkbox" />보고서 파일명에 날짜 포함</label><label>PDF 출력 형식<select defaultValue="a4"><option value="a4">A4 세로</option></select></label></div><p>작업지시서 승인 상태와 보고서 파일은 서버 API에 기록됩니다.</p></section></div></SurfaceCard>}
      </div>
      <aside className="settings-aside"><SurfaceCard title="현재 적용 정책"><ApiState empty={false} error={policy.isError} loading={policy.isLoading} retry={() => void policy.refetch()} />{policy.data && <ul className="settings-summary"><li><span>자동화 모드</span><StatusBadge tone="success">{policy.data.mode}</StatusBadge></li><li><span>최소 신뢰도</span><strong>{(policy.data.minimum_confidence * 100).toFixed(0)}%</strong></li><li><span>승인 최소 비율</span><strong>{(policy.data.minimum_approval_rate * 100).toFixed(0)}%</strong></li><li><span>근거 신뢰도</span><strong>{(policy.data.minimum_source_trust * 100).toFixed(0)}%</strong></li></ul>}</SurfaceCard><SurfaceCard title="저장 범위"><ul className="history-list"><li>알림 채널: 이 브라우저에 저장</li><li>운영 임계값: 백엔드 정책 API에 저장</li><li>보고서·작업지시서: 서버 실행 기록에 저장</li></ul></SurfaceCard></aside>
    </div>{saved && <div className="toast-success">변경 사항을 저장했습니다.</div>}{updatePolicy.isError && <div className="toast-success">운영 정책 저장에 실패했습니다. 백엔드 연결을 확인해 주세요.</div>}
  </div>
}
