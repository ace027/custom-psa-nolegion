import { defineConfig } from "@playwright/test";

// Specs run against a RUNNING stack (dev servers or docker compose), or an isolated one via scripts/e2e.sh: see docs/DEVELOPMENT.md.
export default defineConfig({
  testDir: "e2e",
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
});
