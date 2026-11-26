import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

const screenshotDir = path.resolve(
  process.env.ATLAS_FIGMA_SCREENSHOT_DIR ?? process.env.ATLAS_E2E_ARTIFACT_DIR ?? "../../var/figma-acceptance/screenshots",
);

async function capture(page: import("@playwright/test").Page, name: string): Promise<void> {
  mkdirSync(screenshotDir, { recursive: true });
  await page.screenshot({ path: path.join(screenshotDir, name), fullPage: true, animations: "disabled" });
}

test("capture populated Overview, CRM, and Assistant screens", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await signInAsSeedAdmin(page);
  await expect(page.getByRole("heading", { name: "Customer activity" })).toBeVisible();
  await capture(page, "overview-desktop.png");

  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer records", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Leads", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Leads", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("tbody")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Companies", exact: true })).toHaveAttribute("aria-selected", "false");
  await page.mouse.move(1200, 80);
  await capture(page, "crm-desktop.png");

  const leadButtons = page.locator("tbody button");
  const leadCount = await leadButtons.count();
  if (leadCount > 0) {
    await leadButtons.last().click();
    await expect(page.getByRole("button", { name: "Archive" })).toBeVisible();
    await capture(page, "crm-detail-desktop.png");
  }

  await page.getByRole("link", { name: "Assistant", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Assistant", exact: true })).toBeVisible();
  await capture(page, "assistant-desktop.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/overview");
  await expect(page.getByTestId("overview-workspace")).toBeVisible();
  await capture(page, "overview-mobile.png");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer records", exact: true })).toBeVisible();
  await capture(page, "crm-mobile.png");
});

test("capture primary product screens at desktop and mobile widths", async ({ page }) => {
  test.setTimeout(180_000);
  await signInAsSeedAdmin(page);

  const screens = [
    ["overview", "/overview"],
    ["crm", "/crm?tab=leads"],
    ["assistant", "/assistant"],
    ["workflows", "/workflows"],
    ["knowledge", "/knowledge"],
    ["inbox", "/inbox"],
    ["campaigns", "/campaigns"],
    ["agent-runs", "/agent-runs"],
    ["approvals", "/approvals"],
    ["analytics", "/analytics"],
    ["monitoring", "/monitoring"],
    ["integrations", "/integrations"],
    ["setup", "/setup"],
    ["settings", "/settings"],
  ] as const;

  for (const [form, width, height] of [["desktop", 1440, 960], ["mobile", 390, 844]] as const) {
    await page.setViewportSize({ width, height });
    for (const [name, route] of screens) {
      await page.goto(route);
      await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      if (name === "analytics") await expect(page.getByTestId("analytics-metric-leads")).toBeVisible();
      if (name === "workflows") await expect(page.getByRole("complementary", { name: "Workflow library" })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${route} at ${width}px`).toBeLessThanOrEqual(1);
      await capture(page, `${name}-${form}-${width}x${height}.png`);
    }
  }
});
