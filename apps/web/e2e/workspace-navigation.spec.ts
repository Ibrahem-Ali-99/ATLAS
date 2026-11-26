import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

test("workspace search and Billing remain usable on desktop and mobile", async ({ page }) => {
  await signInAsSeedAdmin(page);
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.keyboard.press("Control+k");
  const search = page.getByRole("dialog", { name: "Search workspace" });
  await expect(search.getByRole("textbox")).toBeFocused();
  await search.getByRole("textbox").fill("billing");
  await search.getByRole("link", { name: "Billing" }).click();
  await expect(page).toHaveURL(/\/billing$/);
  await expect(page.getByRole("heading", { name: "Current subscription" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Usage availability" }).getByText("Knowledge storage")).toBeVisible();
  const directory = process.env.ATLAS_E2E_ARTIFACT_DIR;
  if (directory) {
    mkdirSync(directory, { recursive: true });
    await page.screenshot({ path: path.join(directory, "billing-desktop-1440x960.png") });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Breadcrumb")).toHaveText("Billing", { useInnerText: true });
  if (directory) await page.screenshot({ path: path.join(directory, "billing-mobile-390x844.png") });
  await page.getByRole("button", { name: "Search workspace" }).click();
  await search.getByRole("textbox").fill("inbox");
  await search.getByRole("link", { name: "Inbox" }).click();
  await expect(page.getByRole("heading", { name: "Inbox", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test("Overview creates an opportunity from the mobile workspace", async ({ page }) => {
  const title = `Workspace opportunity ${Date.now()}`;
  await signInAsSeedAdmin(page);
  const directory = process.env.ATLAS_E2E_ARTIFACT_DIR;
  await page.setViewportSize({ width: 1440, height: 960 });
  await expect(page.getByRole("heading", { name: "Pipeline overview" })).toBeVisible();
  if (directory) {
    mkdirSync(directory, { recursive: true });
    await page.screenshot({ path: path.join(directory, "overview-desktop-1440x960.png") });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  if (directory) await page.screenshot({ path: path.join(directory, "overview-mobile-390x844.png") });
  await page.getByRole("button", { name: "New opportunity" }).click();
  const dialog = page.getByRole("dialog", { name: "New opportunity" });
  await dialog.getByLabel("Opportunity name").fill(title);
  await dialog.getByRole("button", { name: "Create opportunity" }).click();
  await page.getByRole("link", { name: "Open pipeline" }).click();
  await page.getByRole("button", { name: new RegExp(title) }).click();
  await expect(page).toHaveURL(/tab=opportunities&id=[a-f0-9-]+/);
  const selected = page.getByRole("dialog", { name: title });
  await expect(selected).toBeVisible();
  await page.reload();
  await expect(selected).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(selected).toHaveCount(0);
});
