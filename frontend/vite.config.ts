import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // In development, `npm run dev` forwards API calls to `uv run harness`.
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
