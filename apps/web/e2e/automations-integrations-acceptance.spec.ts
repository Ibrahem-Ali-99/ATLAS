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
  await expect(page.getByRole("button", { name: "Discover", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Search integrations")).toBeVisible();
  await expect(page.getByLabel("Filter integrations by category")).toBeVisible();

  await page.getByLabel("Search integrations").fill("language");
  await expect(page.getByRole("heading", { name: "Language model", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Email", exact: true })).toHaveCount(0);
  await page.getByLabel("Search integrations").fill("");
  await page.getByLabel("Filter integrations by category").selectOption("Messaging");
  await page.getByRole("button", { name: "Email settings", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Email", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Email delivery", exact: true })).toBeVisible();
  await expect(page.getByText("MAILPIT SANDBOX", { exact: true })).toBeVisible();
  await page.getByText("Prepare live SMTP and Resend").click();
  await expect(page.getByLabel("Resend API key")).toHaveAttribute("type", "password");
  await page.getByLabel("SMTP security").selectOption("tls");
  await expect(page.getByLabel("SMTP password")).toHaveAttribute("type", "password");
  await page.getByLabel("SMTP username").fill("operator@example.test");
  await expect(page.getByRole("button", { name: "Save email settings" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Email settings", exact: true })).toBeFocused();
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
  await expect(page.getByRole("heading", { name: "Workflows", level: 1 })).toBeVisible();
  await page.getByText("Built-in automation activity", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Overview", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Approvals", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Human approvals", exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Open approvals/ }).click();
  await expect(page).toHaveURL(/\/approvals$/);
  await page.goto("/workflows");
  await page.getByText("Built-in automation activity", { exact: true }).click();
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
      const activity = page.getByText("Built-in automation activity", { exact: true });
      if (!await page.getByRole("button", { name: "Email activity", exact: true }).isVisible()) await activity.click();
    }
  }
  await page.getByRole("button", { name: "Email activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Email activity", exact: true })).toBeVisible();
  await shot(page, "automations-desktop.png");
  expect(pageErrors).toEqual([]);
});

test("n8n signing keys can be issued and disconnected from Integrations", async ({ page }) => {
  await signInAsSeedAdmin(page);
  await page.goto("/integrations");
  await page.getByRole("button", { name: "n8n settings" }).click();
  const dialog = page.getByRole("dialog", { name: "n8n", exact: true });
  await dialog.getByRole("button", { name: "Create signing key" }).click();
  await expect(dialog.getByLabel("Signing secret")).not.toHaveValue("");
  await dialog.getByRole("button", { name: "Hide secret" }).click();
  await expect(dialog.getByLabel("Signing secret")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Disconnect n8n" }).click();
  await dialog.getByRole("button", { name: "Confirm disconnect" }).click();
  await expect(dialog.getByText("Disconnected", { exact: true })).toBeVisible();
});

test("staff sees integrations read-only and mobile navigation remains usable", async ({ page }) => {
  await signInAsSeedStaff(page);
  await page.goto("/integrations");
  await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
  await expect(page.getByText("Read only", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Email settings", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Email settings", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Email", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save email settings" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Revoke key" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("link", { name: "Workflows", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Integrations", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Workflows", level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await shot(page, "automations-staff-mobile.png");
});
