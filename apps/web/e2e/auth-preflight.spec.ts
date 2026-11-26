import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

test("disposable API accepts the seeded admin and opens the workspace", async ({ page }) => {
  await signInAsSeedAdmin(page);
  await expect(page.getByRole("link", { name: "Knowledge", exact: true })).toBeVisible();
});

test("an administrator can invite a teammate who joins through a single-use link", async ({ page, browser }) => {
  const email = `invited-${Date.now()}@example.com`;
  await signInAsSeedAdmin(page);
  await page.goto("/settings");
  await page.getByRole("link", { name: "Open billing" }).click();
  await expect(page.getByRole("heading", { name: "Billing", exact: true })).toBeVisible();
  await page.getByLabel("Billing plan").selectOption("starter");
  await page.getByRole("button", { name: "Choose plan" }).click();
  await expect(page.getByText("Subscription updated in sandbox mode.")).toBeVisible();
  await page.goto("/settings");
  await page.getByLabel("Teammate email").fill(email);
  await page.getByRole("button", { name: "Create invitation", exact: true }).click();
  const input = page.getByLabel("Invitation link");
  await expect(input).toBeVisible();
  const url = new URL(await input.inputValue());
  expect(url.pathname).toBe("/invite/accept");
  expect(url.search).toBe("");

  const guest = await browser.newContext();
  try {
    const invitee = await guest.newPage();
    await invitee.goto(url.href);
    await invitee.getByLabel("Full name").fill("Invited teammate");
    await invitee.getByLabel("Password", { exact: true }).fill("disposable-invitation-password");
    await invitee.getByRole("button", { name: "Accept invitation" }).click();
    await expect(invitee).toHaveURL(/\/overview$/);
    await expect(invitee.getByRole("main")).toBeVisible();
    await invitee.goto(url.href);
    await invitee.getByLabel("Full name").fill("Invited teammate");
    await invitee.getByLabel("Password", { exact: true }).fill("disposable-invitation-password");
    await invitee.getByRole("button", { name: "Accept invitation" }).click();
    await expect(invitee.getByText(/this invitation is invalid or expired/i)).toBeVisible();
    if (process.env.ATLAS_E2E_SKIP_MAILPIT === "1") {
      await invitee.goto("/forgot-password");
      await invitee.getByLabel("Email", { exact: true }).fill(email);
      await invitee.getByRole("button", { name: "Send reset link" }).click();
      await expect(invitee.getByText(/if the account exists/i)).toBeVisible();
      const api = `http://127.0.0.1:${process.env.ATLAS_E2E_API_PORT ?? "8011"}`;
      const outbox = await invitee.request.get(`${api}/_acceptance/mail`, { params: { recipient: email } });
      expect(outbox.ok()).toBe(true);
      const messages = await outbox.json() as { subject: string; body: string }[];
      const resetLink = messages.find((item) => item.subject === "Reset your ATLAS password")?.body.trim().split("\n").at(-1);
      expect(resetLink?.startsWith(`${url.origin}/reset-password#token=`)).toBe(true);
      await invitee.goto(resetLink!);
      await invitee.getByLabel("New password", { exact: true }).fill("disposable-recovery-password");
      await invitee.getByLabel("Confirm new password", { exact: true }).fill("disposable-recovery-password");
      await invitee.getByRole("button", { name: "Update password" }).click();
      await expect(invitee.getByText("Password updated. Sign in with your new password.")).toBeVisible();
      await invitee.getByRole("link", { name: "Back to sign in" }).click();
      await invitee.getByLabel("Email").fill(email);
      await invitee.getByLabel("Password", { exact: true }).fill("disposable-recovery-password");
      await invitee.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(invitee).toHaveURL(/\/overview$/);
    }
  } finally {
    await guest.close();
  }
});
