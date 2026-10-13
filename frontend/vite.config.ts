import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom', // a simulated browser, so components can render inside Node
    setupFiles: ['./src/test/setup.ts'],
    env: {
      // Tests never talk to the real backend; every request goes to a mocked fetch.
      VITE_API_URL: 'http://api.test',
      // A timezone west of UTC, so a "date shows one day early" bug can't hide in tests.
      TZ: 'America/Vancouver',
    },
  },
})
