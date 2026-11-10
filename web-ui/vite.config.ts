import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
const backend = process.env.BIGBRAIN_DEV_BACKEND || 'http://localhost:3007';
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 3011,
    // Dev proxy: the BigBrain web server (python -m bigbrain --web).
    proxy: {
      '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
      '/api': { target: backend },
      '/static': { target: backend },
      '/cad-engine': { target: backend },
      '/cad-qualification-fixture': { target: backend },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
