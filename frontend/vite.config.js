import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/video_feed': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  // Vitest config — happy-dom is faster than jsdom for our component tests
  // and we don't need anything jsdom-only (yet). Tests live under tests/
  // at the frontend root; setup.js wires in @testing-library/jest-dom
  // matchers (toBeInTheDocument, etc.) and globals.
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.test.{js,jsx}'],
  },
})