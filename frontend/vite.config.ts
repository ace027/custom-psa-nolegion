/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// No @types/node in this project; only the env is needed here.
declare const process: { env: Record<string, string | undefined> };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // In dev the API is same-origin from the browser's point of view, like behind Caddy.
    proxy: { "/api": `http://localhost:${process.env.E2E_API_PORT ?? 8000}` },
  },
  test: { include: ["src/**/*.test.{ts,tsx}"], environment: "jsdom", setupFiles: ["./src/test-setup.ts"], globals: true },
});
