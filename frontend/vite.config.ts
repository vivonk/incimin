import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server on 5173. Port 3000 is Memgraph Lab (see docs/PORTS.md), so the
// common React default must not be used here.
//
// /api and /webhook proxy to the FastAPI app so the browser sees one origin in
// dev; in production the built assets are served by that same app.
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind IPv4 loopback explicitly. Vite 8 defaults to `localhost`, which resolves
    // to [::1] only — every other service in this project is on 127.0.0.1 per
    // docs/PORTS.md, and the mismatch is a confusing "connection refused".
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Allow ngrok tunnel hostname (and any *.ngrok.app subdomain) so the dev
    // server accepts requests forwarded through the tunnel.
    allowedHosts: ['incimin.ngrok.app', '.ngrok.app'],
    proxy: {
      '/api': { target: 'http://127.0.0.1:8088', changeOrigin: true },
      '/webhook': { target: 'http://127.0.0.1:8088', changeOrigin: true },
    },
  },
})
