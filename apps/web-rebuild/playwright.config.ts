import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const appRoot = __dirname;
const webPort = process.env.ATLAS_E2E_WEB_PORT ?? "3012";
const apiPort = process.env.ATLAS_E2E_API_PORT ?? "8012";

process.env.ATLAS_E2E_WEB_PORT = webPort;
process.env.ATLAS_E2E_API_PORT = apiPort;
process.env.ATLAS_E2E_SKIP_MAILPIT = "1";

function withLocalNode(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  if (process.platform !== "win32" || !env.USERPROFILE) {
    return env;
  }
  const nodeBin = path.join(env.USERPROFILE, ".local", "node");
  return { ...env, PATH: `${nodeBin}${path.delimiter}${env.PATH ?? ""}` };
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    viewport: { width: 1280, height: 800 },
  },
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  webServer: {
    command: `npm run dev -- --hostname 127.0.0.1 --port ${webPort}`,
    cwd: appRoot,
    env: withLocalNode({
      ...process.env,
      ATLAS_API_URL: `http://127.0.0.1:${apiPort}`,
      NEXT_DIST_DIR: ".next-e2e-rebuild",
    }),
    url: `http://127.0.0.1:${webPort}/login`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
