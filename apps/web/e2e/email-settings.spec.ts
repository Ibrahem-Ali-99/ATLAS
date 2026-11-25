import { expect, test } from "@playwright/test";
import path from "node:path";
import { signInAsSeedAdmin } from "./auth";

test("admin manages sandbox email settings and sender domain", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signInAsSeedAdmin(page);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible();
  await expect(page.getByText("MAILPIT SANDBOX", { exact: true })).toBeVisible();
  await page.getByLabel("SMTP host").fill("127.0.0.1");
  await page.getByLabel("SMTP port").fill("1025");
  await page.getByLabel("Sender address").fill("noreply@example.test");
  await page.getByLabel("Resend verification token").fill("e2e-resend-token");
  await page.getByRole("button", { name: "Save email settings" }).click();
  await expect(page.getByText("Delivery remains Mailpit sandbox-only")).toBeVisible();
  await page.getByPlaceholder("mail.example.com").fill("example.test");
  await page.getByRole("button", { name: "Register domain" }).click();
  await expect(page.getByText("pending")).toBeVisible();
  await expect(page.getByText("resend-verification=e2e")).toBeVisible();
  await page.getByRole("button", { name: "Refresh status" }).click();
  await expect(page.getByText("verified")).toBeVisible();
  await page.screenshot({ path: path.resolve(process.cwd(), "../../var/email-settings-desktop.png"), fullPage: true });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("revoked")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.resolve(process.cwd(), "../../var/email-settings-mobile.png"), fullPage: true });
});
