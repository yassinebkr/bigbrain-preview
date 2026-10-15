import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 3011,
    // Dev proxy: the BigBrain web server (python -m bigbrain --web).
    proxy: {
      '/ws': { target: 'ws://localhost:3007', ws: true },
      '/api': { target: 'http://localhost:3007' },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
