import { useEffect, useState, type KeyboardEvent } from 'react'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { ScenarioVersionRail } from './ScenarioVersionRail'
import type { EvaluationCategory, ScenarioAlert, ScenarioState } from './types'

const evaluationOptions: readonly { readonly value: EvaluationCategory; readonly label: string; readonly description: string }[] = [
  { value: 'model', label: '예측 모델 문제', description: '위험도·리드타임 판단이 부정확합니다.' },
  { value: 'external-data', label: '외부 데이터 품질 문제', description: '기상·외부 맥락 데이터가 적합하지 않습니다.' },
  { value: 'rag', label: 'RAG 문서 최신성 문제', description: '검색 근거 또는 매뉴얼이 오래되었습니다.' },
  { value: 'work-order', label: '작업지시서 문구 문제', description: '현장 절차와 지시 문구가 부정확합니다.' },
]

interface Props {
  readonly alert: ScenarioAlert
  readonly state: ScenarioState
  readonly onCancelProposal: () => void
  readonly onAccept: (version: 1 | 2 | 3) => void
  readonly onConfirmProposal: () => void
  readonly onPostMessage: (content: string) => void
  readonly onSubmitEvaluation: (category: EvaluationCategory) => void
}

export function ScenarioWorkOrderWorkspace({ alert, state, onAccept, onCancelProposal, onConfirmProposal, onPostMessage, onSubmitEvaluation }: Props) {
  const [message, setMessage] = useState('')
  const [rerunning, setRerunning] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState<1 | 2 | 3 | null>(null)
  const latestOrder = state.workOrders.at(-1)

  useEffect(() => {
    if (!rerunning) return undefined
    const timer = window.setTimeout(() => {
      onConfirmProposal()
      setRerunning(false)
    }, 1_200)
    return () => window.clearTimeout(timer)
  }, [onConfirmProposal, rerunning])

  if (!latestOrder) return <SurfaceCard title="작업지시서"><div className="scenario-report-empty"><StatusBadge tone="neutral">작업지시서 대기</StatusBadge><p>조치 계획 탭에서 작업지시서를 먼저 생성하세요.</p></div></SurfaceCard>

  const selectedOrder = state.workOrders.find((order) => order.version === selectedVersion) ?? latestOrder

  const sendMessage = () => {
    if (!message.trim() || state.evaluationRequired || rerunning || state.proposal != null) return
    onPostMessage(message)
    setMessage('')
  }

  const submitReviewOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    sendMessage()
  }

  return <div className="scenario-order-layout">
    <SurfaceCard className="scenario-version-panel" title="작업지시서 버전"><ScenarioVersionRail acceptedVersion={state.acceptedWorkOrderVersion} latestVersion={latestOrder.version} messages={state.messages} onSelect={setSelectedVersion} orders={state.workOrders} selectedVersion={selectedOrder.version} /></SurfaceCard>
    {selectedOrder && <SurfaceCard action={<span className="scenario-document-status">문서 내부 스크롤</span>} className="scenario-order-document" title={`작업지시서 v${selectedOrder.version}`}><div aria-label="작업지시서 본문" className="scenario-order-body"><header><div><span>문서번호 HG-20200113-{alert.substationId}-v{selectedOrder.version}</span><h2>{selectedOrder.title}</h2></div><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority}</StatusBadge></header><dl><div><dt>대상 설비</dt><dd>{alert.facility}</dd></div><div><dt>출동 기한</dt><dd>감지 시점부터 <span className="scenario-lead-time">{alert.leadTimeHours}시간</span> 이내</dd></div><div><dt>담당</dt><dd>현장 운전팀</dd></div></dl>{selectedOrder.sections.map((section) => <section key={section.title}><h3>{section.title}</h3><ol>{section.items.map((item) => <li key={item}>{item}</li>)}</ol></section>)}<footer className="scenario-order-accept"><span>{state.acceptedWorkOrderVersion === selectedOrder.version ? '이 버전이 보고서 발행 기준입니다.' : '현장 검토 후 이 버전을 최종 작업지시서로 채택하세요.'}</span><Button icon="check" onClick={() => onAccept(selectedOrder.version)} tone="primary">{state.acceptedWorkOrderVersion === selectedOrder.version ? '최종 채택됨' : '최종 채택'}</Button></footer></div></SurfaceCard>}
    <SurfaceCard className="scenario-chat-card" title="자연어 검토 챗봇"><div className="scenario-chat"><div className="scenario-chat-source"><StatusBadge tone="primary">시나리오 분석</StatusBadge><span>의도를 파악해 에이전트 단계를 다시 실행하고 다음 작업지시서 버전을 만듭니다.</span></div><div className="scenario-chat-messages">{state.messages.length === 0 && <p>모델 평가, 외부 데이터, RAG 문서 또는 작업지시서 문구의 문제를 자유롭게 입력하세요.</p>}{state.messages.map((item) => <article className={item.role} key={item.id}><strong>{item.role === 'operator' ? '운영자' : item.role === 'assistant' ? 'AI 검토' : '실행 결과'}</strong><span>{item.content}</span></article>)}</div><div className="scenario-chat-input"><label htmlFor="scenario-chat-message">검토 의견</label><textarea aria-describedby="scenario-chat-hint" disabled={state.evaluationRequired || rerunning} id="scenario-chat-message" onChange={(event) => setMessage(event.target.value)} onKeyDown={submitReviewOnEnter} placeholder={'예: 참고한 매뉴얼이 오래된 것 같아.\n최신 문서로 다시 확인해줘.'} value={message} /><span id="scenario-chat-hint">Enter 전송 · Shift+Enter 줄바꿈</span><Button disabled={!message.trim() || state.evaluationRequired || rerunning || state.proposal != null} onClick={sendMessage} tone="primary">의견 분석</Button></div>{state.proposal && <div className="scenario-proposal"><header><div><span>파악한 사용자 의도</span><strong>{state.proposal.targetLabel}</strong></div><StatusBadge tone="warning">실행 확인 필요</StatusBadge></header><p>{state.proposal.changeSummary}</p><dl><div><dt>다시 실행할 단계</dt><dd>{state.proposal.targetLabel}</dd></div><div><dt>변경 산출물</dt><dd>작업지시서 v{Math.min(3, state.workOrders.length + 1)}</dd></div></dl><div><Button disabled={rerunning} onClick={() => setRerunning(true)} tone="primary">{rerunning ? '해당 단계 재실행 중' : '수정 실행'}</Button><Button disabled={rerunning} onClick={onCancelProposal}>취소</Button></div></div>}{state.evaluationRequired && !state.improvementCandidate && <div className="scenario-evaluation"><header><h3>재시도 2회를 모두 사용했습니다</h3><p>에이전트 개선을 위해 가장 큰 문제를 선택해 주세요.</p></header><div>{evaluationOptions.map((option) => <button key={option.value} onClick={() => onSubmitEvaluation(option.value)} type="button"><strong>{option.label}</strong><span>{option.description}</span></button>)}</div></div>}{state.improvementCandidate && <div className="scenario-candidate"><StatusBadge tone="success">평가 접수</StatusBadge><div><strong>{state.improvementCandidate.label}</strong><span>실제 자동 실행 없이 개선 후보로 등록했으며 현재 상태는 승인 대기입니다.</span></div><StatusBadge tone="warning">승인 대기</StatusBadge></div>}</div></SurfaceCard>
  </div>
}
