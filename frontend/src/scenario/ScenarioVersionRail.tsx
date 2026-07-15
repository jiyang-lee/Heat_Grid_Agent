import { StatusBadge } from '../console/ui'
import type { ScenarioChatMessage, WorkOrderVersion } from './types'

interface Props {
  readonly acceptedVersion: 1 | 2 | 3 | null
  readonly latestVersion: 1 | 2 | 3
  readonly messages: readonly ScenarioChatMessage[]
  readonly onSelect: (version: 1 | 2 | 3) => void
  readonly orders: readonly WorkOrderVersion[]
  readonly selectedVersion: 1 | 2 | 3
}

function messageRole(role: ScenarioChatMessage['role']): string {
  if (role === 'operator') return '운영자'
  if (role === 'assistant') return 'AI 검토'
  return '실행 결과'
}

export function ScenarioVersionRail({ acceptedVersion, latestVersion, messages, onSelect, orders, selectedVersion }: Props) {
  return <nav aria-label="작업지시서 버전과 검토 이력" className="scenario-version-list">{orders.map((order) => {
    const reviewMessages = messages.filter((message) => message.workOrderVersion === order.version)
    const status = order.version === acceptedVersion ? '채택' : order.version === latestVersion ? '현재' : '이전'
    return <section className="scenario-version-entry" key={order.version}>
      <button aria-pressed={selectedVersion === order.version} className={selectedVersion === order.version ? 'active' : ''} onClick={() => onSelect(order.version)} type="button"><span>v{order.version}</span><div><strong>{order.title}</strong><small>{order.changeSummary}</small></div><StatusBadge tone={status === '채택' ? 'success' : status === '현재' ? 'primary' : 'neutral'}>{status}</StatusBadge></button>
      {reviewMessages.length > 0 && <ol aria-label={`작업지시서 v${order.version} 검토 대화`} className="scenario-version-thread">{reviewMessages.map((message) => <li className={message.role} key={message.id}><b>{messageRole(message.role)}</b><span>{message.content}</span></li>)}</ol>}
    </section>
  })}</nav>
}
