import { useMemo, useState } from 'react'
import type { PolicyCandidate } from '../api/contracts'
import { useDecidePolicyCandidate, useHealth, useOperationsMetrics, usePolicyCandidates, useReviewTasks } from '../api/hooks'
import { Icon } from './icons'
import { users } from './mockViewData'
import { ApiState, Button, MetricCard, StatusBadge, SurfaceCard, type Tone } from './ui'

function userTone(value: string): Tone { return value === '활성' ? 'success' : 'notice' }

function policyTone(status: PolicyCandidate['status']): Tone {
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'critical'
  return 'warning'
}

const policyStatusLabels: Record<PolicyCandidate['status'], string> = {
  pending: '대기', approved: '승인', rejected: '거절',
}

/** v3-02 운영 지표 — GET /api/agent-operations/metrics */
function OperationsMetricsCard() {
  const metrics = useOperationsMetrics()
  const m = metrics.data
  return <SurfaceCard title="AI 운영 지표 (실데이터)">
    <ApiState empty={false} error={metrics.isError} loading={metrics.isLoading} retry={() => void metrics.refetch()} />
    {m && <ul className="system-list">
      <li>전체 AI 실행<strong>{m.run_count}건</strong></li>
      <li>검토 대기<strong>{m.pending_review_count}건</strong></li>
      <li>승인 / 교정 / 사람검토<strong>{m.approved_review_count} / {m.corrected_review_count} / {m.keep_human_review_count}</strong></li>
      <li>승인율<strong>{(m.approval_rate * 100).toFixed(0)}%</strong></li>
      <li>교정율<strong>{(m.correction_rate * 100).toFixed(0)}%</strong></li>
      <li>진단 완료 / 초과 / 무효<strong>{m.diagnostic_completed_count} / {m.diagnostic_timeout_count + m.diagnostic_budget_exceeded_count} / {m.diagnostic_invalid_count}</strong></li>
      <li>정책 후보 대기 / 승인 / 거절<strong>{m.policy_candidate_pending_count} / {m.policy_candidate_approved_count} / {m.policy_candidate_rejected_count}</strong></li>
    </ul>}
  </SurfaceCard>
}

/** v3-02 정책 후보 — 교정 검토 기반, 승인해도 런타임 자동 반영은 없음(v4 입력) */
function PolicyCandidatesCard() {
  const candidates = usePolicyCandidates()
  const decide = useDecidePolicyCandidate()
  const items = candidates.data?.items ?? []
  const act = (candidate: PolicyCandidate, approve: boolean) =>
    decide.mutate({ candidateId: candidate.candidate_id, approve, body: { expected_version: candidate.version, reviewer: 'ops-manager', reason: approve ? '관리자 콘솔에서 승인' : '관리자 콘솔에서 거절' } })
  return <SurfaceCard action={<span className="count-chip">전체 {items.length}</span>} title="AI 정책 후보 (교정 검토 기반)">
    <ApiState empty={items.length === 0 && !candidates.isLoading} error={candidates.isError} loading={candidates.isLoading} retry={() => void candidates.refetch()} />
    {items.length > 0 && <ol className="policy-list">{items.map((candidate) => <li key={candidate.candidate_id}>
      <header><StatusBadge tone={policyTone(candidate.status)}>{policyStatusLabels[candidate.status]}</StatusBadge><strong>{candidate.scope}</strong><small>v{candidate.version} · {new Intl.DateTimeFormat('ko-KR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(candidate.created_at))}</small></header>
      <pre className="policy-proposal">{JSON.stringify(candidate.proposal, null, 1)}</pre>
      {candidate.status === 'pending' && <div className="policy-actions"><Button disabled={decide.isPending} onClick={() => act(candidate, true)} tone="primary">승인</Button><Button disabled={decide.isPending} onClick={() => act(candidate, false)} tone="danger">거절</Button></div>}
    </li>)}</ol>}
    {decide.isError && <p className="form-error">정책 후보 결정을 저장하지 못했습니다. 버전 충돌(409)일 수 있으니 새로고침 후 다시 시도해 주세요.</p>}
    <p className="policy-note">승인된 정책 후보는 v3 런타임에 자동 반영되지 않고 v4 정책 반영 입력으로만 남습니다.</p>
  </SurfaceCard>
}

const roles = [
  { role: '운영센터 관리자', scope: '전체 접근, 설정 변경, 사용자 관리', tone: 'critical' },
  { role: '모니터링 담당자', scope: '모니터링, 알림 관리, 보고서 조회', tone: 'primary' },
  { role: '현장 점검 담당자', scope: '설비 상태 확인, 작업 등록, 조치', tone: 'success' },
  { role: '외부 정비업체', scope: '작업 등록, 조치 보고, 문서 업로드', tone: 'warning' },
  { role: '읽기 전용', scope: '대시보드/보고서 조회 전용', tone: 'neutral' },
] as const satisfies readonly { readonly role: string; readonly scope: string; readonly tone: Tone }[]

export function AdminPage() {
  const [query, setQuery] = useState('')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [message, setMessage] = useState('')
  const health = useHealth()
  const reviews = useReviewTasks()
  const filteredUsers = useMemo(() => users.filter((user) => user.join(' ').toLowerCase().includes(query.toLowerCase())), [query])
  const record = (text: string) => {
    const records = JSON.parse(window.localStorage.getItem('heatgrid:admin-actions') ?? '[]') as string[]
    window.localStorage.setItem('heatgrid:admin-actions', JSON.stringify([`${new Date().toISOString()} ${text}`, ...records].slice(0, 20)))
    setMessage(`${text} (이 브라우저의 관리자 작업 이력에 기록됨)`)
  }
  const invite = () => { setInviteOpen(false); record('사용자 초대 링크를 생성했습니다.') }
  const serviceOk = health.data?.database === 'connected' && health.data.openai === 'configured'
  return <div className="page-stack admin-page"><header className="page-title"><div><h1>관리자 콘솔</h1><p>운영 사용자, 권한과 시스템 상태를 관리합니다.</p></div><div><Button icon="users" onClick={() => setInviteOpen(true)} tone="primary">사용자 초대</Button><Button icon="shield" onClick={() => record('권한 그룹 생성 요청을 등록했습니다.')}>권한 그룹 생성</Button></div></header><div className="metric-grid metric-grid-five"><MetricCard icon="users" label="전체 사용자" value="128명" hint="운영 명단 기준" /><MetricCard icon="shield" label="활성 관리자" value="18명" hint="권한 명단 기준" tone="success" /><MetricCard icon="users" label="권한 그룹" value="6개" hint="역할 템플릿" tone="notice" /><MetricCard icon="clock" label="승인 대기" value={String(reviews.data?.length ?? 0)} hint="실제 검토 작업 API" tone="warning" /><MetricCard icon="activity" label="시스템 상태" value={serviceOk ? '정상' : '확인 필요'} hint="실시간 API/모델 연결" tone={serviceOk ? 'success' : 'warning'} /></div><div className="admin-layout"><div className="admin-main"><SurfaceCard action={<label className="inline-search"><input onChange={(event) => setQuery(event.target.value)} placeholder="사용자 검색" value={query} /><Icon name="search" /></label>} title="사용자 관리"><div className="table-scroll"><table className="ops-table"><thead><tr><th>이름</th><th>역할</th><th>소속</th><th>담당 권역</th><th>최근 접속</th><th>상태</th><th>권한 수정</th></tr></thead><tbody>{filteredUsers.map((user) => <tr key={user[0]}><td><span className="avatar">{user[0].slice(0, 1)}</span><strong>{user[0]}<small>{user[0].toLowerCase()}@heatgrid.kr</small></strong></td><td><StatusBadge tone={user[1].includes('관리자') ? 'critical' : 'primary'}>{user[1]}</StatusBadge></td><td>{user[2]}</td><td>{user[3]}</td><td>2026-07-11 14:18</td><td><StatusBadge tone={userTone(user[4])}>{user[4]}</StatusBadge></td><td><Button aria-label={`${user[0]} 권한 수정`} onClick={() => record(`${user[0]} 권한 수정 요청을 등록했습니다.`)}>수정</Button></td></tr>)}</tbody></table></div><footer className="table-footer"><span>1 - {filteredUsers.length} / 128</span><span>1　2　3　4　5　…　13</span></footer></SurfaceCard><SurfaceCard action={<Button icon="building" onClick={() => record('건물/열원기지 등록 요청을 등록했습니다.')}>건물/열원기지 등록</Button>} title="조직 / 설비 관리"><div className="tab-list"><button className="active" type="button">건물/열원기지</button><button onClick={() => record('권역 목록을 선택했습니다.')} type="button">권역</button><button onClick={() => record('설비 유형 목록을 선택했습니다.')} type="button">설비 유형</button></div><div className="table-scroll"><table className="ops-table"><thead><tr><th>구분</th><th>명칭</th><th>권역</th><th>주소</th><th>담당 관리자</th><th>상태</th><th>설비 수</th></tr></thead><tbody>{[['열원기지', '목동 열원기지', '서울 서남권', '서울특별시 양천구 목동서로 159', '김현장', '정상', '12'], ['열원기지', '상암 열원기지', '서울 서북권', '서울특별시 마포구 상암산로 48', '이모니', '정상', '9'], ['건물', '코엑스 열공급소', '서울 강남권', '서울특별시 강남구 영동대로 513', '김현장', '정상', '6']].map((row) => <tr key={row[1]}>{row.map((cell, index) => <td key={`${row[1]}-${cell}`}>{index === 5 ? <StatusBadge tone="success">{cell}</StatusBadge> : cell}</td>)}</tr>)}</tbody></table></div></SurfaceCard><PolicyCandidatesCard /></div><aside className="admin-aside"><OperationsMetricsCard /><SurfaceCard title="권한 그룹 및 역할"><ul className="role-list">{roles.map((role) => <li key={role.role}><StatusBadge tone={role.tone}>{role.role}</StatusBadge><span>{role.scope}</span></li>)}</ul></SurfaceCard><SurfaceCard title="시스템 관리"><ul className="system-list"><li>검토 대기 작업<strong>{reviews.data?.length ?? 0}건</strong></li><li>백엔드 API<StatusBadge tone={health.data?.database === 'connected' ? 'success' : 'warning'}>{health.data?.database ?? '확인 중'}</StatusBadge></li><li>데이터 수집<StatusBadge tone={health.data?.input === 'postgresql' ? 'success' : 'warning'}>{health.data?.input ?? '확인 중'}</StatusBadge></li><li>모델 서비스<StatusBadge tone={health.data?.openai === 'configured' ? 'success' : 'warning'}>{health.data?.openai ?? '확인 중'}</StatusBadge></li><li>RAG 서비스<StatusBadge tone={health.data?.rag === 'pgvector' ? 'success' : 'warning'}>{health.data?.rag ?? '확인 중'}</StatusBadge></li></ul></SurfaceCard><SurfaceCard title="관리자 동작"><ul className="history-list"><li>초대·권한·등록 요청은 이 브라우저에 기록됩니다.</li><li>실행 승인과 시스템 상태는 실제 백엔드 API를 사용합니다.</li></ul></SurfaceCard></aside></div>{inviteOpen && <div aria-modal="true" className="modal-backdrop" role="dialog"><form className="invite-modal" onSubmit={(event) => { event.preventDefault(); invite() }}><header><h2>사용자 초대</h2><Button aria-label="닫기" icon="x" onClick={() => setInviteOpen(false)} /></header><label>이름<input required placeholder="이름" /></label><label>이메일<input required placeholder="operator@heatgrid.kr" type="email" /></label><label>역할<select defaultValue="monitor"><option value="monitor">모니터링 담당자</option><option value="field">현장 점검 담당자</option><option value="admin">운영센터 관리자</option></select></label><footer><Button onClick={() => setInviteOpen(false)}>취소</Button><Button tone="primary" type="submit">초대 링크 생성</Button></footer></form></div>}{message && <div className="toast-success">{message}</div>}</div>
}
