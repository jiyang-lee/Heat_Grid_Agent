import { useCallback, useState, type ReactNode } from 'react'
import { Button } from './ui'

interface ConfirmRequest {
  readonly message: string
  readonly resolve: (value: boolean) => void
}

export interface ConfirmDialogController {
  readonly confirm: (message: string) => Promise<boolean>
  readonly dialog: ReactNode
}

/**
 * window.confirm 대체용 — 브라우저 네이티브 다이얼로그(주소 표시) 대신
 * 대시보드 스타일 모달로 동일한 await 기반 흐름을 유지한다.
 */
export function useConfirmDialog(): ConfirmDialogController {
  const [request, setRequest] = useState<ConfirmRequest | null>(null)

  const confirm = useCallback((message: string) => new Promise<boolean>((resolve) => {
    setRequest({ message, resolve })
  }), [])

  const settle = (value: boolean) => {
    request?.resolve(value)
    setRequest(null)
  }

  const dialog = request && (
    <div className="modal-backdrop" onClick={() => settle(false)}>
      <div aria-modal="true" className="invite-modal confirm-modal" onClick={(event) => event.stopPropagation()} role="alertdialog">
        {request.message.split('\n').map((line, index) => <p key={index}>{line}</p>)}
        <footer><Button onClick={() => settle(false)}>취소</Button><Button onClick={() => settle(true)} tone="primary">확인</Button></footer>
      </div>
    </div>
  )

  return { confirm, dialog }
}
