import { execFileSync, spawn } from "node:child_process";
import { readFileSync, unlinkSync } from "node:fs";
import path from "node:path";

function stopRecordedProcess(pid: number): Promise<void> {
  if (process.platform !== "win32") {
    try {
      process.kill(-pid, "SIGTERM");
    } catch {
      try {
        process.kill(pid, "SIGTERM");
      } catch {
        // The API process was already stopped.
      }
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
  const apiPort = process.env.ATLAS_E2E_API_PORT ?? "8011";
  const databaseName = process.env.ATLAS_E2E_DATABASE_NAME ?? "";
  if (!/^atlas_e2e_[0-9a-f]{32}$/.test(databaseName)) return;
  const pidFile = path.resolve(process.cwd(), `../../var/${databaseName}.pid`);
  try {
    const pid = Number(readFileSync(pidFile, "utf8"));
    if (Number.isInteger(pid) && pid > 0) await stopRecordedProcess(pid);
    unlinkSync(pidFile);
  } catch {
    // The API process was already stopped.
  }
  const mailpitFile = path.resolve(process.cwd(), `../../var/e2e-mailpit-${apiPort}.name`);
  const mailpitHttpFile = path.resolve(process.cwd(), `../../var/e2e-mailpit-${apiPort}.http-port`);
  try {
    const name = readFileSync(mailpitFile, "utf8").trim();
    if (name) execFileSync("docker", ["rm", "-f", name], { stdio: "ignore" });
    unlinkSync(mailpitFile);
    unlinkSync(mailpitHttpFile);
  } catch {
    // The disposable Mailpit was already removed.
  }
}
