import { expect, test } from "@playwright/test";

const screenshots = "D:/ATLAS/.pytest-tmp/phase2d-screenshots";

async function signIn(page: import("@playwright/test").Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible({ timeout: 10_000 });
}

test("admin settings expose editable provider controls and fallback state", async ({ page }) => {
  await signIn(page, "admin@example.com", "change-me-admin");
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Administrator access")).toBeVisible();
  await expect(page.locator("select").first()).toBeEnabled();
  await expect(page.getByLabel("Model").first()).toBeEnabled();
  await expect(page.getByLabel("API key").first()).toHaveAttribute("type", "password");
  await expect(page.getByText(/Using environment default|Fallback|Key installed/).first()).toBeVisible();
  await page.screenshot({ path: `${screenshots}/settings-admin-desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible({ timeout: 10_000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${screenshots}/settings-admin-mobile.png`, fullPage: true });
});

test("organization selection switches and persists the workspace", async ({ page }) => {
  await signIn(page, "admin@example.com", "change-me-admin");
  const selector = page.getByLabel("Organization");
  await expect(selector).toBeVisible();
  await expect(selector.locator("option")).toHaveCount(2);
  await selector.selectOption({ label: "Northwind" });
  await page.goto("/settings");
  await expect(page.getByText("Northwind", { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Organization")).toHaveValue(await selector.inputValue());
  await page.screenshot({ path: `${screenshots}/settings-northwind.png`, fullPage: true });
});

test("staff settings are read-only", async ({ page }) => {
  await signIn(page, "staff@example.com", "change-me-staff");
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Read only").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Test connection" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Revoke key" })).toHaveCount(0);
  await page.screenshot({ path: `${screenshots}/settings-staff-desktop.png`, fullPage: true });
});

test("admin saves and persists a disposable organization override", async ({ page }) => {
  await signIn(page, "admin@example.com", "change-me-admin");
  await page.goto("/settings");
  const model = page.getByLabel("Model").first();
  const key = page.getByLabel("API key").first();
  await model.fill("openai/gpt-oss-20b");
  await key.fill("disposable-settings-fixture-key");
  await page.getByRole("button", { name: "Save" }).first().click();
  await expect(page.getByRole("status")).toContainText("Configuration saved", { timeout: 10_000 });
  await expect(key).toHaveValue("");
  await page.reload();
  await expect(page.getByText(/Key installed/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByLabel("API key").first()).toHaveValue("");
  await expect(page.getByText(/version/).first()).toBeVisible();
  await page.screenshot({ path: `${screenshots}/settings-save-persisted.png`, fullPage: true });
});

test("admin disable confirmation persists and staff cannot mutate", async ({ page }) => {
  await signIn(page, "admin@example.com", "change-me-admin");
  await page.goto("/settings");
  await page.on("dialog", (dialog) => dialog.accept());
  if (await page.getByRole("button", { name: "Enable" }).count()) {
    await page.getByRole("button", { name: "Enable" }).first().click();
    await expect(page.getByRole("status")).toContainText(/enabled/i, { timeout: 10_000 });
  }
  await page.getByRole("button", { name: "Disable" }).first().click();
  await expect(page.getByRole("status")).toContainText(/disabled/i, { timeout: 10_000 });
  await page.reload();
  await expect(page.getByText(/disabled/).first()).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "staff@example.com", "change-me-staff");
  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Disable" })).toHaveCount(0);
  await page.screenshot({ path: `${screenshots}/settings-disabled-staff.png`, fullPage: true });
});

test("indexed knowledge blocks incompatible embedding changes", async ({ page }) => {
  await signIn(page, "admin@example.com", "change-me-admin");
  await page.getByLabel("Organization").selectOption({ label: "Northwind" });
  await page.goto("/settings");
  await expect(page.getByLabel("Vector dimensions")).toHaveValue("768");
  await page.getByLabel("Vector dimensions").selectOption("1536");
  await expect(page.getByText(/require a full reindex/i)).toBeVisible();
  await page.getByRole("button", { name: "Save" }).nth(1).click();
  await expect(page.getByRole("status")).toContainText(/requires an explicit reindex/i, { timeout: 10_000 });
  await page.reload();
  await expect(page.getByLabel("Vector dimensions")).toHaveValue("768");
  await page.screenshot({ path: `${screenshots}/settings-embedding-rejection.png`, fullPage: true });
});

test("provider connection verification reports success, invalid credentials, and timeout", async ({ page }) => {
  await signIn(page, "admin@example.com", "change-me-admin");
  await page.goto("/settings");
  const key = page.getByLabel("API key").first();
  const save = page.getByRole("button", { name: "Save" }).first();
  const verify = page.getByRole("button", { name: "Test connection" }).first();
  await key.fill("e2e-success");
  await save.click();
  await expect(page.getByRole("status")).toContainText("Configuration saved");
  await verify.click();
  await expect(page.getByRole("status")).toContainText("Provider verification succeeded.", { timeout: 10_000 });
  await expect(page.getByText("e2e-success")).toHaveCount(0);
  await key.fill("e2e-invalid");
  await save.click();
  await verify.click();
  await expect(page.getByRole("status")).toContainText(/Verification failed: The language model rejected the API key/i, { timeout: 10_000 });
  await key.fill("e2e-timeout");
  await save.click();
  const started = Date.now();
  await verify.click();
  await expect(page.getByRole("status")).toContainText(/Verification failed: The language model timed out/i, { timeout: 10_000 });
  expect(Date.now() - started).toBeLessThan(10_000);
  await page.screenshot({ path: `${screenshots}/settings-connection-verification.png`, fullPage: true });
});
