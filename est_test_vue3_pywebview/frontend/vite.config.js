import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [
    vue(),
    {
      name: 'favicon-fallback',
      configureServer(server) {
        server.middlewares.use('/favicon.ico', (req, res) => {
          res.statusCode = 204
          res.end()
        })
      },
    },
  ],
  base: './',
  build: {
    outDir: 'dist',
  },
})

