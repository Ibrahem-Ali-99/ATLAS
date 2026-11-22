import { type ChildProcess, spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const apiRoot = path.resolve(process.cwd(), "../api");
const repoRoot = path.resolve(process.cwd(), "../..");
const pidFile = path.join(repoRoot, "var", "e2e-api.pid");

async function waitForHealth(url: string): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // The API process is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("The e2e API did not become ready");
}

function spawnApi(): ChildProcess {
  return spawn("uv", ["run", "python", "-m", "app.scripts.e2e_server"], {
    cwd: apiRoot,
    env: process.env,
    stdio: "ignore",
  });
}

export default async function globalSetup(): Promise<void> {
  const prepare = spawn("uv", ["run", "python", "-m", "app.scripts.e2e_database"], {
    cwd: apiRoot,
    stdio: "inherit",
    env: process.env,
  });
  const code = await new Promise<number>((resolve) => {
    prepare.on("exit", (status) => resolve(status ?? 1));
  });
  if (code !== 0) {
    throw new Error("The e2e database was not prepared");
  }
  const api = spawnApi();
  if (api.pid === undefined) {
    throw new Error("The e2e API did not start");
  }
  mkdirSync(path.dirname(pidFile), { recursive: true });
  writeFileSync(pidFile, String(api.pid), "utf8");
  try {
    await waitForHealth("http://127.0.0.1:8010/api/v1/ready");
  } catch (error) {
    api.kill();
    throw error;
  }
}
