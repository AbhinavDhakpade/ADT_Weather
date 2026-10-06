import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // All requests to /api/* are forwarded to Django on port 8000.
      // Because the request now appears to come from the same origin (Vite),
      // the browser never sends a CORS preflight — this eliminates the entire
      // class of "Could not reach the AgriAura server" CORS errors.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
