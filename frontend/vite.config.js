import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api= process.env.API_URL || "http://localhost:8000";
const mapa= process.env.MAPA_URL;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: api, rewrite: (caminho) => caminho.replace(/^\/api/, "") },
      ...(mapa ? { "/mapa": { target: mapa } } : {}),
    },
  },
});
