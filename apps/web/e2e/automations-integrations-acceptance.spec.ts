import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin, signInAsSeedStaff } from "./auth";

const artifactDir = path.resolve(process.env.ATLAS_E2E_ARTIFACT_DIR ?? path.resolve(process.cwd(), "../../var/automations-integrations-browser"));

async function shot(page: import("@playwright/test").Page, name: string): Promise<void> {
  mkdirSync(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, name), fullPage: true });
}

test("admin can inspect persisted integrations and automation activity", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await signInAsSeedAdmin(page);
  await page.goto("/integrations");
  await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
  await expect(page.getByText("Administrator access", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Search integrations")).toBeVisible();
  await expect(page.getByLabel("Filter integrations by category")).toBeVisible();

  await page.getByLabel("Search integrations").fill("language");
  await expect(page.getByRole("heading", { name: "Language model", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Email delivery", exact: true })).toHaveCount(0);
  await page.getByLabel("Search integrations").fill("");
  await page.getByLabel("Filter integrations by category").selectOption("email");
  await expect(page.getByRole("heading", { name: "Email delivery", exact: true })).toBeVisible();
  await expect(page.getByText("MAILPIT SANDBOX", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Resend verification token")).toHaveAttribute("type", "password");
  await expect(page.getByLabel("Search integrations")).toBeVisible();
  await shot(page, "integrations-admin-desktop.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await shot(page, "integrations-admin-mobile.png");

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/automations");
  await expect(page).toHaveURL(/\/workflows$/);
  await expect(page.getByRole("heading", { name: "Automations", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Overview", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Approvals", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Human approvals", exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Open approvals/ }).click();
  await expect(page).toHaveURL(/\/approvals$/);
  await page.goto("/workflows");
  await page.getByRole("button", { name: "Execution history", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Execution history", exact: true })).toBeVisible();
  await page.getByLabel("Search execution history").fill("unlikely-no-match");
  await expect(page.getByText("No workflow runs are stored for this view.", { exact: true })).toBeVisible();
  await page.getByLabel("Search execution history").fill("");
  await page.getByLabel("Filter execution history").selectOption("completed");
  await expect(page.getByLabel("Filter execution history")).toHaveValue("completed");

  const inspectButtons = page.getByRole("button", { name: /Inspect .* (Completed|Failed|Running|Awaiting approval|Needs attention)/ });
  if (await inspectButtons.count() > 0) {
    await inspectButtons.first().click();
    await expect(page.getByRole("region", { name: "Execution details" })).toBeVisible();
    const relatedLead = page.getByRole("region", { name: "Execution details" }).getByRole("link", { name: /Open related lead/ });
    if (await relatedLead.count() > 0) {
      await relatedLead.click();
      await expect(page).toHaveURL(/\/crm\?tab=leads&id=/);
      await page.goBack();
    }
  }
  await page.getByRole("button", { name: "Email activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Email activity", exact: true })).toBeVisible();
  await shot(page, "automations-desktop.png");
  expect(pageErrors).toEqual([]);
});

test("staff sees integrations read-only and mobile navigation remains usable", async ({ page }) => {
  await signInAsSeedStaff(page);
  await page.goto("/integrations");
  await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
  await expect(page.getByText("Read only", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Revoke key" })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("link", { name: "Automations", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Integrations", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Automations", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Automations", level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await shot(page, "automations-staff-mobile.png");
});
