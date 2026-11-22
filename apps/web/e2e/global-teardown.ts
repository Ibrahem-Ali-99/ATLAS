import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

export default async function globalTeardown(): Promise<void> {
  const pidFile = path.resolve(process.cwd(), "../../var/e2e-api.pid");
  try {
    const pid = Number(readFileSync(pidFile, "utf8"));
    if (!Number.isFinite(pid)) {
      return;
    }
    await new Promise<void>((resolve) => {
      const killer = spawn("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
      killer.on("exit", () => resolve());
    });
  } catch {
    // The API process was already stopped.
  }
}
