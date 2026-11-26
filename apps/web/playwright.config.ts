import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const e2eWebPort = process.env.ATLAS_E2E_WEB_PORT ?? "3011";
const e2eApiPort = process.env.ATLAS_E2E_API_PORT ?? "8011";
const e2eProduction = process.env.ATLAS_E2E_PRODUCTION === "1";

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
    baseURL: `http://127.0.0.1:${e2eWebPort}`,
    trace: "retain-on-failure",
    actionTimeout: 20_000,
  },
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  webServer: process.env.ATLAS_E2E_EXTERNAL_WEB === "1" ? undefined : {
    command: e2eProduction
      ? `npm run build && npm run start -- --hostname 127.0.0.1 --port ${e2eWebPort}`
      : `npm run dev -- --hostname 127.0.0.1 --port ${e2eWebPort}`,
    url: `http://127.0.0.1:${e2eWebPort}/login`,
    // Production acceptance must exercise the build selected by NEXT_DIST_DIR;
    // reusing an older process can silently serve stale markup and test IDs.
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...withLocalNode(process.env),
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? `http://127.0.0.1:${e2eApiPort}`,
      ATLAS_E2E_API_PORT: e2eApiPort,
      ATLAS_E2E_WEB_PORT: e2eWebPort,
      NEXT_DIST_DIR: process.env.NEXT_DIST_DIR ?? ".next-e2e-phase2d",
    },
  },
});
