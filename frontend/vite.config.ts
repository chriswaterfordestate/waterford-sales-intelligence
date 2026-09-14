import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Production API base URL is injected at build time via VITE_API_BASE_URL env var.
// In development, the proxy below routes /api → localhost:8000 (no env var needed).

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  define: {
    // Expose API base URL to frontend code
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(process.env.VITE_API_BASE_URL || ''),
  },
})
