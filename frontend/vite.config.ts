import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const port = parseInt(env.VITE_PORT || '5183')
  const backendUrl = env.VITE_BACKEND_URL || 'http://localhost:8010'
  const backendWs = backendUrl.replace(/^http/, 'ws')

  return {
    plugins: [react()],
    server: {
      port,
      proxy: {
        '/api': backendUrl,
        '/ws': {
          target: backendWs,
          ws: true,
        },
      },
    },
  }
})
