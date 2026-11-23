import { type ChildProcess, spawn } from "node:child_process";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const apiRoot = path.resolve(process.cwd(), "../api");
const repoRoot = path.resolve(process.cwd(), "../..");
const pidFile = path.join(repoRoot, "var", "e2e-api.pid");
const logFile = path.join(repoRoot, "var", "e2e-api.log");
const apiPort = Number(process.env.ATLAS_E2E_API_PORT ?? "8011");

function redacted(value: string): string {
  return value.replace(/(password|secret|api[_-]?key|token)=\S+/gi, "$1=[REDACTED]");
}

async function waitForHealth(url: string, api: ChildProcess): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      if (api.exitCode !== null || api.signalCode !== null) {
        throw new Error(`The e2e API exited before readiness; see ${logFile}`);
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("The e2e API did not become ready");
}

function spawnApi(): Promise<ChildProcess> {
  return new Promise((resolve, reject) => {
    const python = process.platform === "win32"
      ? path.join(apiRoot, ".venv", "Scripts", "python.exe")
      : "python";
    const child = spawn(python, ["-m", "app.scripts.e2e_server"], {
      cwd: apiRoot,
      env: { ...process.env, ATLAS_E2E_API_PORT: String(apiPort), ATLAS_E2E_WEB_PORT: "3011" },
      stdio: ["ignore", "pipe", "pipe"],
      detached: false,
    });
    child.stdout?.on("data", (chunk: Buffer) => appendFileSync(logFile, redacted(chunk.toString())));
    child.stderr?.on("data", (chunk: Buffer) => appendFileSync(logFile, redacted(chunk.toString())));
    child.once("error", reject);
    child.once("spawn", () => {
      if (process.platform !== "win32") {
        child.unref();
      }
      resolve(child);
    });
  });
}

function projectPython(): string {
  return process.platform === "win32"
    ? path.join(apiRoot, ".venv", "Scripts", "python.exe")
    : "python";
}

export default async function globalSetup(): Promise<void> {
  mkdirSync(path.dirname(logFile), { recursive: true });
  writeFileSync(logFile, "e2e API startup\n", "utf8");
  const prepare = spawn(projectPython(), ["-m", "app.scripts.e2e_database"], {
    cwd: apiRoot,
    stdio: "inherit",
    env: process.env,
  });
  const code = await new Promise<number>((resolve) => {
    prepare.once("error", () => resolve(1));
    prepare.once("exit", (status) => resolve(status ?? 1));
  });
  if (code !== 0) {
    throw new Error("The e2e database was not prepared");
  }
  const api = await spawnApi();
  if (api.pid === undefined) {
    throw new Error("The e2e API did not start");
  }
  mkdirSync(path.dirname(pidFile), { recursive: true });
  writeFileSync(pidFile, String(api.pid), "utf8");
  try {
    await waitForHealth(`http://127.0.0.1:${apiPort}/api/v1/ready`, api);
    if (api.exitCode !== null || api.signalCode !== null) {
      throw new Error(`The e2e API exited after readiness; see ${logFile}`);
    }
  } catch (error) {
    api.kill();
    throw error;
  }
}
