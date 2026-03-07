import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5183,
    proxy: {
      '/api': 'http://localhost:8010',
      '/ws': {
        target: 'ws://localhost:8010',
        ws: true,
      },
    },
  },
})
