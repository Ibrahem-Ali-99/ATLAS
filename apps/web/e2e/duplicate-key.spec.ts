import { expect, test } from "@playwright/test";

import { signInAsSeedAdmin } from "./auth";

const routes = [
  "/overview",
  "/crm",
  "/inbox",
  "/campaigns",
  "/knowledge",
  "/assistant",
  "/agent-runs",
  "/approvals",
  "/workflows",
  "/analytics",
  "/monitoring",
  "/integrations",
  "/setup",
  "/settings",
  "/billing",
];

test("workspace pages do not reuse a React key", async ({ page }) => {
  const warnings: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (text.includes("same key")) warnings.push(`${page.url()} ${text}`);
  });
  await signInAsSeedAdmin(page);
  for (const route of routes) {
    await page.goto(route);
    await page.getByRole("main").getByRole("heading", { level: 1 }).waitFor({ timeout: 20_000 });
  }
  await page.waitForTimeout(500);
  expect(warnings, warnings.join("\n")).toEqual([]);
});
