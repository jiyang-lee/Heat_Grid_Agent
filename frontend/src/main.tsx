import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

const devToolsDisabled = new URLSearchParams(window.location.search).get('devtools') === '0'

if (import.meta.env.DEV && import.meta.env.VITE_DISABLE_REACT_DEVTOOLS !== '1' && !devToolsDisabled) {
  void import('react-grab')
  void import('react-scan')
}

// 데이터 계층 토대: alert/agent-run 조회·캐시는 TanStack Query,
// SSE 스트림은 src/api/client.ts의 subscribeSse(native EventSource)로 처리한다.
const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
