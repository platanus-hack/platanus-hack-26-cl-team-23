import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, searchForWorkspaceRoot } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Permite leer el video y los JSON que genera el backend (backend/orchestrator/app/assets)
    // sin copiarlos: si Andrés los regenera, el front los ve al tiro.
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), '../../backend/orchestrator/app/assets'] },
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
