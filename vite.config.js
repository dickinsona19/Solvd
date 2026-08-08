import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'

// Static multi-page site: all copy ships in the initial HTML, no client
// rendering. Crawlers and link previews get the full page with JS disabled.
export default defineConfig({
  server: {
    // Local development keeps browser requests same-origin while the Python
    // API runs on port 8000. Production uses VITE_API_BASE_URL on Render.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/healthz': 'http://127.0.0.1:8000',
    },
  },
  build: {
    // The only chunk over the default 500 kB is accounts/test/visits.json, a
    // six thousand row check-in log. It is data rather than code, it is 56 kB
    // gzipped, and only /app/ ever asks for it. A real deployment would derive
    // server side and never ship the log at all.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        custom: fileURLToPath(
          new URL('./custom/index.html', import.meta.url),
        ),
        demo: fileURLToPath(new URL('./demo/index.html', import.meta.url)),
        login: fileURLToPath(new URL('./login/index.html', import.meta.url)),
        app: fileURLToPath(new URL('./app/index.html', import.meta.url)),
      },
    },
  },
})
