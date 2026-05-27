import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api/pipeline': {
        target: 'http://localhost:8001',
        rewrite: (path) => path.replace(/^\/api\/pipeline/, ''),
        changeOrigin: true,
      },
      '/api/results': {
        target: 'http://localhost:8002',
        rewrite: (path) => path.replace(/^\/api\/results/, ''),
        changeOrigin: true,
      },
      '/api/scheduler': {
        target: 'http://localhost:8003',
        rewrite: (path) => path.replace(/^\/api\/scheduler/, ''),
        changeOrigin: true,
      },
    },
  },
})
