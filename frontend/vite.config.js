import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 백엔드(FastAPI, 기본 8000)로 프록시 — 프론트는 상대경로로 호출.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/priority": "http://127.0.0.1:8000",
      "/agent": "http://127.0.0.1:8000",
    },
  },
});
