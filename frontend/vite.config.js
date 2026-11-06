import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// B1: proxy /api and /model.glb to the backend on 7860 (mock now, C's FastAPI after merge).
// /m is proxied too so the QR code works from the dev server.
// 127.0.0.1 rather than "localhost": on Windows Node resolves localhost to ::1 first,
// and uvicorn (like the mock) listens on IPv4, so "localhost" gives ECONNREFUSED.
const API = "http://127.0.0.1:7860";
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": API,
      "/model.glb": API,
      "^/m/?$": API,
    },
  },
  build: { chunkSizeWarningLimit: 1200 },
});
