import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'

// Static multi-page site: all copy ships in the initial HTML, no client
// rendering. Crawlers and link previews get the full page with JS disabled.
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        custom: fileURLToPath(
          new URL('./custom/index.html', import.meta.url),
        ),
      },
    },
  },
})
