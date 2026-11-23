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
  const pidFile = path.resolve(process.cwd(), "../../var/e2e-api.pid");
  try {
    const pid = Number(readFileSync(pidFile, "utf8"));
    if (!Number.isFinite(pid) || pid <= 0) {
      return;
    }
    await stopRecordedProcess(pid);
  } catch {
    // The API process was already stopped.
  }
  try {
    const name = readFileSync(path.resolve(process.cwd(), "../../var/e2e-mailpit.name"), "utf8").trim();
    execFileSync("docker", ["rm", "-f", name], { stdio: "ignore" });
    unlinkSync(path.resolve(process.cwd(), "../../var/e2e-mailpit.name"));
    unlinkSync(path.resolve(process.cwd(), "../../var/e2e-mailpit.http-port"));
  } catch {
    // The disposable Mailpit was already removed.
  }
}
