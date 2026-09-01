import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  build: {
    assetsInlineLimit: (filePath: string) =>
      // Vite inlines small assets as base64 data: URIs, but
      // AudioWorklet.addModule() rejects them in Safari and Firefox. Worklets
      // must stay real files.
      filePath.includes('.worklet.') ? false : undefined,
  },
})
