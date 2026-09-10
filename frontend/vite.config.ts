import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Адрес запущенного API. Порт 8000 бывает занят другим проектом на той же
// машине — тогда API поднимают на свободном порту и называют его здесь,
// вместо правки конфигурации под себя.
const apiTarget = process.env.BLASTEX_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget,
    },
  },
});
