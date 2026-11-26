import { execFileSync, type ChildProcess, spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const apiRoot = path.resolve(process.cwd(), "../api");
const repoRoot = path.resolve(process.cwd(), "../..");
const apiPort = Number(process.env.ATLAS_E2E_API_PORT ?? "8011");
const mailpitFile = path.join(repoRoot, "var", `e2e-mailpit-${apiPort}.name`);
const mailpitHttpFile = path.join(repoRoot, "var", `e2e-mailpit-${apiPort}.http-port`);
const logFile = path.join(repoRoot, "var", `e2e-api-${apiPort}.log`);
const mailpitName = `atlas-e2e-mailpit-${process.pid}`;
let mailpitPort = 0;

function mappedPort(container: string, target: string): number {
  const output = execFileSync(
    "docker",
    ["inspect", "--format", `{{(index (index .NetworkSettings.Ports \"${target}\") 0).HostPort}}`, container],
    { encoding: "utf8" },
  );
  return Number(output.trim());
}

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
  throw new Error(`The e2e API did not become ready at ${url}; see ${logFile}`);
}

function spawnApi(): Promise<ChildProcess> {
  return new Promise((resolve, reject) => {
    const python = process.platform === "win32"
      ? path.join(apiRoot, ".venv", "Scripts", "python.exe")
      : "python";
    const child = spawn(python, ["-m", "app.scripts.e2e_server"], {
      cwd: apiRoot,
      env: {
        ...process.env,
        ATLAS_E2E_API_PORT: String(apiPort),
        ATLAS_E2E_WEB_PORT: process.env.ATLAS_E2E_WEB_PORT ?? "3011",
        ATLAS_E2E_PROVIDER_TRANSPORT: "1",
        ATLAS_E2E_RESEND_TRANSPORT: "1",
        ATLAS_BILLING_PROVIDER: "sandbox",
        ATLAS_EMAIL_LIVE_ENABLED: "false",
        ATLAS_COOKIE_SECURE: "false",
        ATLAS_ENVIRONMENT: "development",
        ATLAS_SMTP_HOST: "127.0.0.1",
        ATLAS_SMTP_PORT: String(mailpitPort),
      },
      stdio: ["ignore", "pipe", "pipe"],
      detached: false,
    });
    child.stdout?.on("data", (chunk: Buffer) => appendFileSync(logFile, redacted(chunk.toString())));
    child.stderr?.on("data", (chunk: Buffer) => appendFileSync(logFile, redacted(chunk.toString())));
    child.once("error", reject);
    child.once("spawn", () => {
      child.unref();
      resolve(child);
    });
  });
}

async function startMailpit(): Promise<void> {
  execFileSync("docker", [
    "run", "-d", "--rm", "--name", mailpitName,
    "-p", "127.0.0.1::1025", "-p", "127.0.0.1::8025", "axllent/mailpit:v1.21",
  ], { stdio: "ignore" });
  mailpitPort = mappedPort(mailpitName, "1025/tcp");
  if (!mailpitPort) throw new Error("The disposable Mailpit port was not allocated");
  writeFileSync(mailpitFile, mailpitName, "utf8");
  const httpPortNumber = mappedPort(mailpitName, "8025/tcp");
  if (!httpPortNumber) throw new Error("The disposable Mailpit HTTP port was not allocated");
  writeFileSync(mailpitHttpFile, String(httpPortNumber), "utf8");
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${httpPortNumber}/api/v1/info`);
      if (response.ok) return;
    } catch {
      // Mailpit is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Disposable Mailpit did not become ready");
}

function mailpitRequired(): boolean {
  return process.env.ATLAS_E2E_SKIP_MAILPIT !== "1";
}

function projectPython(): string {
  return process.platform === "win32"
    ? path.join(apiRoot, ".venv", "Scripts", "python.exe")
    : "python";
}

export default async function globalSetup(): Promise<() => void> {
  mkdirSync(path.dirname(logFile), { recursive: true });
  writeFileSync(logFile, "e2e API startup\n", "utf8");
  const databaseName = `atlas_e2e_${randomUUID().replaceAll("-", "")}`;
  process.env.ATLAS_E2E_DATABASE_NAME = databaseName;
  process.env.ATLAS_STORAGE_DIR = path.join(repoRoot, "var", databaseName, "uploads");
  process.env.ATLAS_MODEL_DIR = path.join(repoRoot, "var", databaseName, "models");
  const pidFile = path.join(repoRoot, "var", `${databaseName}.pid`);
  const e2eEnvironment = {
    ...process.env,
    // Docker's published port is a host IPv4 endpoint on Windows. Avoid the
    // localhost IPv6-first resolution path during disposable database setup.
    POSTGRES_HOST: process.env.ATLAS_E2E_POSTGRES_HOST ?? process.env.POSTGRES_HOST ?? "127.0.0.1",
    ATLAS_E2E_POSTGRES_HOST: process.env.ATLAS_E2E_POSTGRES_HOST ?? process.env.POSTGRES_HOST ?? "127.0.0.1",
  };
  process.env.POSTGRES_HOST = e2eEnvironment.POSTGRES_HOST;
  process.env.ATLAS_E2E_POSTGRES_HOST = e2eEnvironment.ATLAS_E2E_POSTGRES_HOST;
  const prepare = spawn(projectPython(), ["-m", "app.scripts.e2e_database"], {
    cwd: apiRoot,
    stdio: "inherit",
    env: e2eEnvironment,
  });
  const code = await new Promise<number>((resolve) => {
    const timer = setTimeout(() => {
      if (process.platform === "win32" && prepare.pid) {
        execFileSync("taskkill", ["/PID", String(prepare.pid), "/T", "/F"], { stdio: "ignore" });
      } else {
        prepare.kill();
      }
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
    throw new Error(`The e2e database was not prepared (exit ${code}); verify PostgreSQL readiness and inspect the setup output.`);
  }
  if (mailpitRequired()) {
    await startMailpit();
  } else {
    mailpitPort = 1025;
    writeFileSync(mailpitFile, "", "utf8");
    writeFileSync(mailpitHttpFile, "", "utf8");
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
    api.stdout?.destroy();
    api.stderr?.destroy();
    throw error;
  }
  return () => {
    api.stdout?.destroy();
    api.stderr?.destroy();
  };
}
