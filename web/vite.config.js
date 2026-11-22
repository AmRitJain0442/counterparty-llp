import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The FastAPI app serves web/dist and /api from one origin in production.
// In development, point /api at a locally running backend (default port 8080).
const api = process.env.COUNTERPARTY_API || 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: api, changeOrigin: false } } },
  build: { sourcemap: false, rollupOptions: { input: ['index.html', 'workspace.html'] } },
})
