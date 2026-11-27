import { type ChildProcess, spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const appRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(appRoot, "../..");
const apiRoot = path.resolve(repoRoot, "apps/api");
const apiPort = process.env.ATLAS_E2E_API_PORT ?? "8012";
const logFile = path.join(repoRoot, "var", `e2e-api-${apiPort}.log`);
const nameFile = path.join(repoRoot, "var", `e2e-rebuild-${apiPort}.name`);

function projectPython(): string {
  return process.platform === "win32"
    ? path.join(apiRoot, ".venv", "Scripts", "python.exe")
    : "python";
}

function redacted(value: string): string {
  return value.replace(/(password|secret|api[_-]?key|token)=\S+/gi, "$1=[REDACTED]");
}

async function waitForHealth(url: string, api: ChildProcess): Promise<void> {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      if (api.exitCode !== null || api.signalCode !== null) {
        throw new Error(`The e2e API exited before readiness; see ${logFile}`);
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`The e2e API did not become ready at ${url}; see ${logFile}`);
}

export default async function globalSetup(): Promise<void> {
  mkdirSync(path.dirname(logFile), { recursive: true });
  writeFileSync(logFile, "replacement client e2e API startup\n", "utf8");
  const databaseName = `atlas_e2e_${randomUUID().replaceAll("-", "")}`;
  process.env.ATLAS_E2E_DATABASE_NAME = databaseName;
  process.env.ATLAS_E2E_SKIP_MAILPIT = "1";
  process.env.ATLAS_STORAGE_DIR = path.join(repoRoot, "var", databaseName, "uploads");
  process.env.ATLAS_MODEL_DIR = path.join(repoRoot, "var", databaseName, "models");
  const host = process.env.ATLAS_E2E_POSTGRES_HOST ?? process.env.POSTGRES_HOST ?? "127.0.0.1";
  process.env.POSTGRES_HOST = host;
  process.env.ATLAS_E2E_POSTGRES_HOST = host;
  writeFileSync(nameFile, `${databaseName}\n`, "utf8");

  const prepare = spawn(projectPython(), ["-m", "app.scripts.e2e_database"], {
    cwd: apiRoot,
    stdio: "inherit",
    env: process.env,
  });
  const code = await new Promise<number>((resolve) => {
    const timer = setTimeout(() => {
      prepare.kill();
      resolve(124);
    }, 120_000);
    prepare.once("error", () => {
      clearTimeout(timer);
      resolve(1);
    });
    prepare.once("exit", (status) => {
      clearTimeout(timer);
      resolve(status ?? 1);
    });
  });
  if (code !== 0) {
    throw new Error(`The e2e database was not prepared (exit ${code}).`);
  }

  const api = spawn(projectPython(), ["-m", "app.scripts.e2e_server"], {
    cwd: apiRoot,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  api.stdout?.on("data", (chunk: Buffer) => appendFileSync(logFile, redacted(chunk.toString())));
  api.stderr?.on("data", (chunk: Buffer) => appendFileSync(logFile, redacted(chunk.toString())));
  if (api.pid === undefined) {
    throw new Error("The e2e API did not start");
  }
  writeFileSync(path.join(repoRoot, "var", `${databaseName}.pid`), String(api.pid), "utf8");
  api.unref();
  await waitForHealth(`http://127.0.0.1:${apiPort}/api/v1/ready`, api);
}
