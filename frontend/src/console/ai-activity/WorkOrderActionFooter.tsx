import type { ReactNode } from 'react'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

interface Props {
  readonly saveStatus: SaveStatus
  readonly saveErrorDetail?: string | null
  readonly notice?: string | null
  readonly children: ReactNode
}

const SAVE_STATUS_LABEL: Record<SaveStatus, string> = {
  idle: '',
  saving: '저장 중…',
  saved: '저장 완료',
  error: '저장 실패 · 다시 시도',
}

/** 작업지시서 상세의 sticky 하단 action bar: 저장 상태 + 안내 문구(좌) / 주요 액션(우). */
export function WorkOrderActionFooter({ saveStatus, saveErrorDetail, notice, children }: Props) {
  return (
    <div className="work-order-action-footer">
      <div className="work-order-action-footer-status">
        {saveStatus !== 'idle' && (
          <span
            className={`work-order-save-status work-order-save-status-${saveStatus}`}
            title={saveStatus === 'error' && saveErrorDetail ? saveErrorDetail : undefined}
          >
            {SAVE_STATUS_LABEL[saveStatus]}
          </span>
        )}
        {notice && <span className="work-order-action-footer-notice">{notice}</span>}
      </div>
      <div className="work-order-action-footer-actions">{children}</div>
    </div>
  )
}
