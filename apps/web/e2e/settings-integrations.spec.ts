import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { signInAsSeedAdmin, signInAsSeedStaff } from "./auth";
import { openSampleWorkspace, prepareSampleWorkspace, sampleWorkspaceSlug } from "./sample-workspace";

const screenshots = path.resolve(process.env.ATLAS_E2E_ARTIFACT_DIR ?? "../../var/settings-acceptance");
const chatSettings = (page: Page) => page.getByRole("region", { name: "Language model" });
const embeddingSettings = (page: Page) => page.getByRole("region", { name: "Embeddings", exact: true });

test("admin settings expose editable provider controls and fallback state", async ({ page }) => {
  await signInAsSeedAdmin(page);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Administrator access")).toBeVisible();
  await expect(page.locator("select").first()).toBeEnabled();
  await expect(page.getByLabel("Model").first()).toBeEnabled();
  await expect(page.getByLabel("API key").first()).toHaveAttribute("type", "password");
  await expect(page.getByText(/Using the server default|Environment defaults|Fallback|Key installed/).first()).toBeVisible();
  await page.screenshot({ path: `${screenshots}/settings-admin-desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible({ timeout: 10_000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${screenshots}/settings-admin-mobile.png`, fullPage: true });
});
test("organization selection switches and persists the workspace", async ({ page }) => {
  await signInAsSeedAdmin(page);
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
  await signInAsSeedStaff(page);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Read only").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Test connection" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Revoke key" })).toHaveCount(0);
  await page.screenshot({ path: `${screenshots}/settings-staff-desktop.png`, fullPage: true });
});

test.describe("provider configuration", () => {
  const slug = sampleWorkspaceSlug();
  test.beforeAll(async ({ request }) => prepareSampleWorkspace(request, slug, "prepare"));
  test.afterAll(async ({ request }) => prepareSampleWorkspace(request, slug, "cleanup"));

  test("admin saves and persists a disposable organization override", async ({ page }) => {
    await openSampleWorkspace(page);
    await page.goto("/settings");
    const model = chatSettings(page).getByLabel("Model", { exact: true });
    const key = chatSettings(page).getByLabel("API key");
    await model.fill("openai/gpt-oss-20b");
    await key.fill("disposable-settings-fixture-key");
    await chatSettings(page).getByRole("button", { name: "Save", exact: true }).click();
    await expect(chatSettings(page).getByRole("status")).toContainText("Configuration saved", { timeout: 10_000 });
    await expect(key).toHaveValue("");
    await page.reload();
    await expect(chatSettings(page).getByText("Key installed", { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(chatSettings(page).getByLabel("API key")).toHaveValue("");
    await expect(chatSettings(page).getByText(/version/)).toBeVisible();
    await page.screenshot({ path: `${screenshots}/settings-save-persisted.png`, fullPage: true });
  });

  test("admin disable confirmation persists and staff cannot mutate", async ({ page }) => {
    await openSampleWorkspace(page);
    await page.goto("/settings");
    page.on("dialog", (dialog) => dialog.accept());
    const settings = chatSettings(page);
    if (await settings.getByText(/Using the server default|Fallback/).isVisible()) {
      await settings.getByLabel("API key").fill("disposable-toggle-fixture");
      await settings.getByRole("button", { name: "Save", exact: true }).click();
      await expect(settings.getByRole("status")).toContainText("Configuration saved");
    }
    if (await chatSettings(page).getByRole("button", { name: "Enable", exact: true }).count()) {
      await chatSettings(page).getByRole("button", { name: "Enable", exact: true }).click();
      await expect(chatSettings(page).getByRole("status")).toContainText(/enabled/i, { timeout: 10_000 });
    }
    await chatSettings(page).getByRole("button", { name: "Disable", exact: true }).click();
    await expect(chatSettings(page).getByRole("status")).toContainText(/disabled/i, { timeout: 10_000 });
    await page.reload();
    await expect(chatSettings(page).getByText(/disabled/)).toBeVisible();
    await chatSettings(page).getByRole("button", { name: "Enable", exact: true }).click();
    await expect(chatSettings(page).getByRole("status")).toContainText(/enabled/i);
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await signInAsSeedStaff(page);
    await page.goto("/settings");
    await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Disable", exact: true })).toHaveCount(0);
    await page.screenshot({ path: `${screenshots}/settings-disabled-staff.png`, fullPage: true });
  });

  test("indexed knowledge blocks incompatible embedding changes", async ({ page }) => {
    await openSampleWorkspace(page);
    await page.getByLabel("Organization").selectOption({ label: "Northwind" });
    await expect(page.getByLabel("Organization").locator("option:checked")).toHaveText("Northwind");
    await page.goto("/settings");
    await expect(embeddingSettings(page).getByLabel("Vector dimensions")).toHaveValue("768");
    await embeddingSettings(page).getByLabel("Vector dimensions").selectOption("1536");
    await expect(page.getByText(/requires a full reindex/i)).toBeVisible();
    await embeddingSettings(page).getByRole("button", { name: "Save", exact: true }).click();
    await expect(embeddingSettings(page).getByRole("status")).toContainText(/replacement index/i, { timeout: 10_000 });
    await page.reload();
    await expect(embeddingSettings(page).getByLabel("Vector dimensions")).toHaveValue("768");
    await page.screenshot({ path: `${screenshots}/settings-embedding-rejection.png`, fullPage: true });
  });

  test("provider connection verification reports success, invalid credentials, and timeout", async ({ page }) => {
    await openSampleWorkspace(page);
    await page.goto("/settings");
    const key = chatSettings(page).getByLabel("API key");
    const save = chatSettings(page).getByRole("button", { name: "Save", exact: true });
    const verify = chatSettings(page).getByRole("button", { name: "Test connection", exact: true });
    await key.fill("e2e-success");
    await save.click();
    await expect(chatSettings(page).getByRole("status")).toContainText("Configuration saved");
    await verify.click();
    await expect(chatSettings(page).getByRole("status")).toContainText("Provider verification succeeded.", { timeout: 10_000 });
    await expect(page.getByText("e2e-success")).toHaveCount(0);
    await key.fill("e2e-invalid");
    await save.click();
    await verify.click();
    await expect(chatSettings(page).getByRole("status")).toContainText(/Verification failed: The language model rejected the API key/i, { timeout: 10_000 });
    await key.fill("e2e-timeout");
    await save.click();
    const started = Date.now();
    await verify.click();
    await expect(chatSettings(page).getByRole("status")).toContainText(/Verification failed: The language model timed out/i, { timeout: 10_000 });
    expect(Date.now() - started).toBeLessThan(10_000);
    await page.screenshot({ path: `${screenshots}/settings-connection-verification.png`, fullPage: true });
  });

  test("stale configuration edits show a conflict without overwriting the newer update", async ({ page, browser }) => {
    await openSampleWorkspace(page);
    await page.goto("/settings");
    const initialModel = chatSettings(page).getByLabel("Model", { exact: true });
    if (await chatSettings(page).getByRole("button", { name: "Save", exact: true }).count()) {
      await initialModel.fill("initial-concurrent-model");
      await Promise.all([
        page.waitForResponse((response) => response.url().includes("integration-configs/chat") && response.request().method() === "PUT"),
        chatSettings(page).getByRole("button", { name: "Save", exact: true }).click(),
      ]);
      await expect(chatSettings(page).getByRole("status")).toContainText("Configuration saved", { timeout: 10_000 });
      await page.reload();
    }
    const sessionB = await browser.newContext();
    const pageB = await sessionB.newPage();
    await openSampleWorkspace(pageB);
    await pageB.goto("/settings");
    const modelB = chatSettings(pageB).getByLabel("Model", { exact: true });
    await modelB.fill("session-b-model");
    await Promise.all([
      pageB.waitForResponse((response) => response.url().includes("integration-configs/chat") && response.request().method() === "PUT"),
      chatSettings(pageB).getByRole("button", { name: "Save", exact: true }).click(),
    ]);
    await expect(chatSettings(pageB).getByRole("status")).toContainText("Configuration saved", { timeout: 10_000 });
    const modelA = chatSettings(page).getByLabel("Model", { exact: true });
    await modelA.fill("stale-session-a-model");
    const staleResponse = page.waitForResponse((response) => response.url().includes("integration-configs/chat") && response.request().method() === "PUT");
    await chatSettings(page).getByRole("button", { name: "Save", exact: true }).click();
    await expect((await staleResponse).status()).toBe(409);
    await expect(page.locator("body")).toContainText(/changed; reload before updating/i, { timeout: 10_000 });
    await page.reload();
    await expect(chatSettings(page).getByLabel("Model", { exact: true })).toHaveValue("session-b-model");
    await page.screenshot({ path: `${screenshots}/settings-version-conflict.png`, fullPage: true });
    await sessionB.close();
  });

  test("invalid CSRF mutation is rejected without a success state", async ({ page }) => {
    await openSampleWorkspace(page);
    await page.goto("/settings");
    await page.route("**/api/v1/organizations/*/integration-configs/chat", async (route) => {
      const headers = { ...route.request().headers() };
      delete headers["x-csrf-token"];
      await route.continue({ headers });
    });
    const model = chatSettings(page).getByLabel("Model", { exact: true });
    await model.fill("csrf-rejected-model");
    await chatSettings(page).getByRole("button", { name: "Save", exact: true }).click();
    await expect(chatSettings(page).getByRole("status")).toContainText(/CSRF token missing or invalid/i, { timeout: 10_000 });
    await expect(chatSettings(page).getByRole("status")).not.toContainText("Configuration saved");
    await page.unroute("**/api/v1/organizations/*/integration-configs/chat");
    await page.reload();
    await expect(chatSettings(page).getByLabel("Model", { exact: true })).not.toHaveValue("csrf-rejected-model");
    await page.screenshot({ path: `${screenshots}/settings-csrf-rejection.png`, fullPage: true });
  });
});
