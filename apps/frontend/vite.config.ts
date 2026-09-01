import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Port 8000 is a common default and is often already in use; PERSONAE_BACKEND
// lets a contributor point the dev server elsewhere without editing this file.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'PERSONAE_')
  const backend = env['PERSONAE_BACKEND'] ?? 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      proxy: {
        // The backend serves /characters, not /api/characters; the prefix
        // exists only so the dev server can tell API calls from client routes.
        '/api': {
          target: backend,
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api/, ''),
        },
        '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
      },
    },
    build: {
      assetsInlineLimit: (filePath: string) =>
        // Vite inlines small assets as base64 data: URIs, but
        // AudioWorklet.addModule() rejects them in Safari and Firefox, so
        // worklets must stay real files.
        filePath.includes('.worklet.') ? false : undefined,
    },
  }
})
