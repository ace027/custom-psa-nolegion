import { defineConfig } from "@playwright/test";

// Smoke test against a RUNNING stack (dev servers or docker compose): see docs/DEVELOPMENT.md.
export default defineConfig({
  testDir: "e2e",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
});
