import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", outputDir: "./test-results/browser", timeout: 30000, expect: {timeout: 8000},
  fullyParallel: true, retries: process.env.CI ? 1 : 0, workers: process.env.CI ? 2 : 1,
  reporter: [["list"]], use: {baseURL: "http://127.0.0.1:3001", trace: "retain-on-failure"},
  projects: [
    {name: "desktop", use: {...devices["Desktop Chrome"]}},
    {name: "mobile", use: {...devices["Pixel 7"]}},
  ],
  // Build first: exercise the deployed artifact without dev/HMR manifest races.
  webServer: {command: "node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3001",
    url: "http://127.0.0.1:3001/interview", timeout: 30000, reuseExistingServer: false},
});
