/**
 * 알림 상세 — 해당 건물명 + 작업지시서(작업 지시서 카드)만 표시.
 * 에이전트 실행/토큰·비용 지표는 상위(OpsConsole)에서 처리하고 결과만 props로 받는다.
 * 작업지시서 카드 골격은 항상 고정 표시하고, 값이 아직 없으면(선택 직후/실행 중) 자리표시자(—)만 보여준다.
 */

import type { AgentRunArtifact, AgentRunResponse, AlertSummary, OpsAgentResultV4 } from '../api/contracts'
import { useAgentIterations } from '../api/hooks'
import { complexById } from '../domain/model'

interface Props {
  alert: AlertSummary | null
  run: AgentRunResponse | null
  opsResult: OpsAgentResultV4 | null
  resultLoading: boolean
  resultError: boolean
  running: boolean
  commandError: boolean
  dailyReport: AgentRunArtifact | null
  dailyReportError: boolean
}

const DASH = '—'

export default function AlertDetail({
  alert,
  run,
  opsResult,
  resultLoading,
  resultError,
  running,
  commandError,
  dailyReport,
  dailyReportError,
}: Props) {
  const iterations = useAgentIterations(run?.status === 'completed' ? run.run_id : null)
  if (!alert) return <div className="empty">왼쪽에서 알림을 선택하세요</div>
  const location = alert.substation_id == null
    ? 'Substation -'
    : `${complexById.get(alert.substation_id)?.name ?? '미등록 단지'} · Substation ${alert.substation_id}`

  const ops = run?.ops_output
  const summary = opsResult?.headline ?? ops?.summary ?? DASH
  const actionPlan = opsResult
    ? opsResult.actions.map((item) => `${item.priority}. ${item.title}\n${item.detail}`).join('\n\n')
    : ops?.action_plan ?? DASH
  const caution = opsResult ? opsResult.cautions.join('\n') : ops?.caution ?? DASH
  const runMode = run?.agent_mode?.toUpperCase() ?? (run ? 'AGENT' : null)

  return (
    <div className="aside-body">
      <div className="aside-meta" style={{ padding: 0, border: 'none' }}>
        <div className="bn">{location} · 전체 {alert.priority_rank ?? '-'}위</div>
        <div className="ba">
          {alert.priority_level} · score {alert.priority_score?.toFixed(1) ?? '-'} · {alert.status}
          {alert.acked_by ? ` · ${alert.acked_by}` : ''}
        </div>
        <div className="ba">평가 {alert.evaluation_run_id ?? '-'} · 기준 {alert.as_of_time ? new Date(alert.as_of_time).toLocaleString('ko-KR') : '-'}</div>
      </div>
      {commandError && <div className="wo-err">작업지시서 생성에 실패했습니다.</div>}
      {dailyReportError && <div className="wo-err">일일 보고서 생성에 실패했습니다.</div>}
      {dailyReport && (
        <div className="ba">
          일일 보고서 ·{' '}
          <a
            href={`/api/agent-runs/${dailyReport.run_id}/artifacts/${dailyReport.artifact_id}/content`}
            target="_blank"
            rel="noreferrer"
          >
            {dailyReport.name}
          </a>
        </div>
      )}

      {/* 작업 지시서(작업지시서 카드) — 골격 항상 고정 표시. */}
      <div className="wo-card">
        <div className="wo-mode">{run ? `${runMode} · ${run.run_id} · ${run.status}` : running ? '작업 지시서 생성 중…' : DASH}</div>
        {run?.loop_summary && (
          <div className="loop-summary">
            <span>반복 <b>{run.loop_summary.iterations}/{run.loop_summary.max_iterations}</b></span>
            <span>근거 <b>{Math.round(run.loop_summary.evidence_score * 100)}%</b></span>
            <span>신뢰 <b>{Math.round(run.loop_summary.confidence * 100)}%</b></span>
            <span>최종 검수 <b>{run.review_status}</b></span>
          </div>
        )}
        {run?.loop_summary?.model_verification && (
          <div className="model-check">
            <div><span>모델 재검증</span><b>{run.loop_summary.model_verification.status}</b></div>
            <div><span>입력 충족</span><b>{Math.round(run.loop_summary.model_verification.feature_coverage * 100)}%</b></div>
            <div><span>기존 결과 일치</span><b>{run.loop_summary.model_verification.agreement == null ? '확인 불가' : run.loop_summary.model_verification.agreement ? '일치' : '불일치'}</b></div>
            <div><span>평가 실행</span><b>{run.loop_summary.model_verification.evaluation_run_id?.slice(0, 8) ?? '-'}</b></div>
            <div><span>Substation</span><b>{run.loop_summary.model_verification.substation_id ?? '-'}</b></div>
          </div>
        )}
        {iterations.data && iterations.data.length > 0 && (
          <div className="ops-timeline">
            {iterations.data.map((item) => (
              <div className="ev" key={item.iteration_id}>
                <span className="ev-t">회차 {item.iteration}</span>
                <span>{item.decision} · 근거 {Math.round(item.evidence_score * 100)}%</span>
              </div>
            ))}
          </div>
        )}
        <div className="wo-sec">
          <div className="wo-k">요약</div>
          <div className="wo-v">{summary}</div>
        </div>
        {opsResult && (
          <>
            <div className="wo-sec">
              <div className="wo-k">상황</div>
              <div className="wo-v">{opsResult.situation}</div>
            </div>
            <div className="wo-sec">
              <div className="wo-k">근거</div>
              <div className="wo-v pre">
                {opsResult.evidence.map((item) => `${item.label}: ${item.content}`).join('\n')}
              </div>
            </div>
          </>
        )}
        {resultLoading && (
          <div className="wo-sec">
            <div className="wo-k">v4 결과</div>
            <div className="wo-v">작업 지시 결과를 불러오는 중입니다.</div>
          </div>
        )}
        {resultError && (
          <div className="wo-sec">
            <div className="wo-k">v4 결과</div>
            <div className="wo-v">기존 작업 지시서 형식으로 표시 중입니다.</div>
          </div>
        )}
        <div className="wo-sec">
          <div className="wo-k">조치 계획</div>
          <div className="wo-v pre">{actionPlan}</div>
        </div>
        <div className="wo-sec">
          <div className="wo-k">주의</div>
          <div className="wo-v pre">{caution}</div>
        </div>
        {opsResult && (
          <details className="wo-report">
            <summary>{opsResult.report.title}</summary>
            <pre>{opsResult.report.content}</pre>
          </details>
        )}
      </div>
    </div>
  )
}
