import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const screenshotDir = path.resolve(
  process.env.ATLAS_FIGMA_SCREENSHOT_DIR ?? "D:/ATLAS/var/figma-acceptance/screenshots",
);

async function capture(page: import("@playwright/test").Page, name: string): Promise<void> {
  mkdirSync(screenshotDir, { recursive: true });
  await page.screenshot({ path: path.join(screenshotDir, name), fullPage: true });
}

async function signIn(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
}

test("capture populated Overview, CRM, and Assistant screens", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await signIn(page);
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

  await page.getByRole("link", { name: "AI Assistant", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Assistant", exact: true })).toBeVisible();
  await capture(page, "assistant-desktop.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/overview");
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await capture(page, "overview-mobile.png");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer records", exact: true })).toBeVisible();
  await capture(page, "crm-mobile.png");
});
