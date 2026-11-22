import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

function withLocalNode(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  if (process.platform !== "win32" || !env.USERPROFILE) {
    return env;
  }
  const nodeBin = path.join(env.USERPROFILE, ".local", "node");
  return { ...env, PATH: `${nodeBin}${path.delimiter}${env.PATH ?? ""}` };
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:3010",
    trace: "retain-on-failure",
  },
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3010",
    url: "http://127.0.0.1:3010/login",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...withLocalNode(process.env),
      NEXT_PUBLIC_API_URL: "http://127.0.0.1:8010",
    },
  },
});
