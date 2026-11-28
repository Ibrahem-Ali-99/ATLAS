import { execFileSync, spawn } from "node:child_process";
import { readFileSync, rmSync, unlinkSync } from "node:fs";
import path from "node:path";

const appRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(appRoot, "../..");
const apiRoot = path.resolve(repoRoot, "apps/api");
const apiPort = process.env.ATLAS_E2E_API_PORT ?? "8012";

function projectPython(): string {
  return process.platform === "win32"
    ? path.join(apiRoot, ".venv", "Scripts", "python.exe")
    : path.join(apiRoot, ".venv", "bin", "python");
}

function stopRecordedProcess(pid: number): Promise<void> {
  if (!Number.isInteger(pid) || pid <= 0) return Promise.resolve();
  if (process.platform !== "win32") {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      // The API process was already stopped.
    }
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const killer = spawn("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    killer.on("error", () => resolve());
    killer.on("exit", () => resolve());
  });
}

export default async function globalTeardown(): Promise<void> {
  const nameFile = path.join(repoRoot, "var", `e2e-rebuild-${apiPort}.name`);
  let databaseName = "";
  try {
    databaseName = readFileSync(nameFile, "utf8").trim();
  } catch {
    return;
  }
  if (!/^atlas_e2e_[0-9a-f]{32}$/.test(databaseName)) return;
  const pidFile = path.join(repoRoot, "var", `${databaseName}.pid`);
  try {
    const pid = Number(readFileSync(pidFile, "utf8"));
    await stopRecordedProcess(pid);
    unlinkSync(pidFile);
  } catch {
    // The API process was already stopped.
  }
  try {
    execFileSync(
      projectPython(),
      ["-c", "from tests.bootstrap import drop_generated_database; import os; drop_generated_database(os.environ['ATLAS_E2E_DATABASE_NAME'])"],
      {
        cwd: apiRoot,
        env: { ...process.env, ATLAS_E2E_DATABASE_NAME: databaseName },
        stdio: "inherit",
      },
    );
  } catch {
    // The disposable database was already removed.
  }
  rmSync(path.join(repoRoot, "var", databaseName), { recursive: true, force: true });
  unlinkSync(nameFile);
}
