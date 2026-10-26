import { defineConfig } from "@playwright/test";

if (
  !process.env.RF_TEST_DATABASE_URL ||
  process.env.RF_TEST_DATABASE_URL !== process.env.RF_DATABASE_URL ||
  !new URL(process.env.RF_TEST_DATABASE_URL).pathname.startsWith("/rf_test_")
) {
  throw new Error(
    "Use backend/.venv/bin/python scripts/test_database.py --browser from the repository root.",
  );
}

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3100",
    browserName: "chromium",
    timezoneId: "Asia/Kolkata",
    channel: process.env.PLAYWRIGHT_CHANNEL ?? "chrome",
  },
  webServer: [
    {
      command:
        "../backend/.venv/bin/python -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8100 --no-access-log",
      url: "http://127.0.0.1:8100/ready",
      reuseExistingServer: false,
    },
    {
      command: "npm run start -- --port 3100",
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
      env: { BACKEND_URL: "http://127.0.0.1:8100" },
    },
  ],
});
