import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_BACKEND_URL || 'http://127.0.0.1:8003'

  return {
    plugins: [react()],
    server: {
      port: Number(process.env.PORT) || 5173,
      // 실 백엔드(simulator v2 postgres_react_ops)로 계약 요청 프록시.
      // 프론트는 상대경로 `/api/...`로만 호출하고, 백엔드 주소는 여기서만 관리한다.
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
        // 서버 루트 엔드포인트(/api prefix 없음)
        '/health': { target: backendTarget, changeOrigin: true },
      },
    },
  }
})
