import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

test("admin manages sandbox email settings and sender domain", async ({ page }) => {
  test.skip(process.env.ATLAS_E2E_RESEND_TRANSPORT !== "1", "Requires the disposable Resend transport");
  await signInAsSeedAdmin(page);
  await page.goto("/integrations");
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible();
  await page.getByRole("button", { name: "Email settings", exact: true }).click();
  const email = page.getByRole("dialog", { name: "Email", exact: true });
  await expect(email.getByText("MAILPIT SANDBOX", { exact: true })).toBeVisible();
  await email.getByLabel("SMTP host").fill("127.0.0.1");
  await email.getByLabel("SMTP port").fill("1025");
  await email.getByLabel("Sender address").fill("noreply@example.test");
  await email.getByLabel("Resend API key").fill("e2e-resend-token");
  await email.getByRole("button", { name: "Save email settings" }).click();
  await expect(email.getByText("Saved. Test the connection and check the sending domain.")).toBeVisible();
  await email.getByPlaceholder("mail.example.com").fill("example.test");
  await email.getByRole("button", { name: "Register domain" }).click();
  await expect(email.getByText("pending", { exact: true })).toBeVisible();
  await expect(email.getByText("resend-verification=e2e")).toBeVisible();
  await email.getByRole("button", { name: "Verify domain" }).click();
  await expect(email.getByText("verified", { exact: true })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await email.getByRole("button", { name: "Revoke", exact: true }).click();
  await expect(email.getByText("revoked", { exact: true })).toBeVisible();
});
