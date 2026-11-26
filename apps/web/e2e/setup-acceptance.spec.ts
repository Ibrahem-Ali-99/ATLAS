import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin, signInAsSeedStaff } from "./auth";

test("an administrator saves setup and staff can review readiness", async ({ page, browser }) => {
  const description = `Customer operations workspace ${Date.now()}`;
  await signInAsSeedAdmin(page);
  await page.goto("/setup");
  await page.getByLabel("Business description").fill(description);
  await page.getByLabel("Timezone").fill("Africa/Cairo");
  await page.getByLabel("Assistant name").fill("Customer Desk");
  const save = page.waitForResponse((response) =>
    response.request().method() === "PATCH" && new URL(response.url()).pathname.endsWith("/onboarding"),
  );
  await page.getByRole("button", { name: "Save setup" }).click();
  expect((await save).ok()).toBe(true);
  await expect(page.getByText("Setup saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Business description")).toHaveValue(description);
  await expect(page.getByLabel("Assistant name")).toHaveValue("Customer Desk");
  const marker = `storage-capacity-${Date.now()}`;
  await page.getByLabel("Choose knowledge document").setInputFiles({
    name: `${marker}.txt`, mimeType: "text/plain", buffer: Buffer.from(`Cold storage reference: ${marker}.`),
  });
  await expect(page.getByText("Indexed and searchable.")).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Assistant test question").fill(marker);
  await page.getByRole("button", { name: "Run assistant test" }).click();
  await expect(page.getByRole("region", { name: "Organization onboarding" }).getByRole("status")).toContainText(`Sources: ${marker}`);
  const checklist = page.getByRole("region", { name: "Setup checklist" });
  await expect(checklist.getByRole("listitem").filter({ hasText: "Index the first document" })).toContainText("Complete");
  await expect(checklist.getByRole("listitem").filter({ hasText: "Verify an answer with citations" })).toContainText("Complete");

  const staffContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  try {
    const staff = await staffContext.newPage();
    await signInAsSeedStaff(staff);
    await staff.goto("/setup");
    const setup = staff.getByRole("main");
    await expect(setup.getByRole("heading", { name: "Setup checklist" })).toBeVisible();
    await expect(setup.getByText("Workspace administrators manage the organization profile and assistant configuration.")).toBeVisible();
    await expect(setup.getByRole("button", { name: "Save setup" })).toHaveCount(0);
    await expect(setup.getByRole("alert")).toHaveCount(0);
  } finally {
    await staffContext.close();
  }
});
