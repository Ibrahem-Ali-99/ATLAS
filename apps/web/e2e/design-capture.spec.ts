import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { signInAsSeedAdmin } from "./auth";

const routes = [
  "overview", "crm", "inbox", "assistant", "knowledge", "approvals", "workflows",
  "agent-runs", "analytics", "campaigns", "monitoring", "integrations", "billing", "settings", "setup",
];
const authRoutes = ["login", "forgot-password", "reset-password", "invite/accept"];
const viewports = [
  { device: "desktop", width: 1440, height: 960 },
  { device: "mobile", width: 390, height: 844 },
];

test("render a viewport capture of every workspace and account page", async ({ page }) => {
  const directory = process.env.ATLAS_E2E_ARTIFACT_DIR;
  test.skip(!directory, "Set ATLAS_E2E_ARTIFACT_DIR to collect design comparison captures");
  if (!directory) return;
  test.setTimeout(240_000);
  const output = path.join(directory, "design-comparison");
  mkdirSync(output, { recursive: true });
  const captures: { route: string; viewport: string; title: string; documentWidth: number }[] = [];
  async function capture(route: string, device: string, width: number, height: number) {
    await page.goto(`/${route}`);
    const heading = page.getByRole("heading", { level: 1 }).first();
    await expect(heading).toBeVisible();
    const title = await heading.innerText();
    const viewport = `${width}x${height}`;
    const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(documentWidth, `${route} at ${viewport}`).toBeLessThanOrEqual(width + 1);
    await page.screenshot({ path: path.join(output, `${route.replaceAll("/", "-")}-${device}-${viewport}.png`), animations: "disabled" });
    captures.push({ route, viewport, title, documentWidth });
  }
  for (const { device, width, height } of viewports) {
    await page.setViewportSize({ width, height });
    for (const route of authRoutes) await capture(route, device, width, height);
  }
  await signInAsSeedAdmin(page);
  for (const { device, width, height } of viewports) {
    await page.setViewportSize({ width, height });
    for (const route of routes) await capture(route, device, width, height);
  }
  writeFileSync(path.join(output, "evidence.json"), JSON.stringify(captures, null, 2));
});
