import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", timeout: 30000, expect: {timeout: 8000},
  fullyParallel: true, retries: process.env.CI ? 1 : 0, workers: process.env.CI ? 2 : 1,
  reporter: [["list"]], use: {baseURL: "http://127.0.0.1:3001", trace: "retain-on-failure"},
  projects: [
    {name: "desktop", use: {...devices["Desktop Chrome"]}},
    {name: "mobile", use: {...devices["Pixel 7"]}},
  ],
  webServer: {command: "node node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 --port 3001",
    url: "http://127.0.0.1:3001/interview", timeout: 90000, reuseExistingServer: !process.env.CI},
});
