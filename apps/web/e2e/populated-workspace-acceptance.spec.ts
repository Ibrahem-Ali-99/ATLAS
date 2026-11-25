import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

const slug = `sample-e2e-${process.pid}-${Date.now()}`;
const artifactDir = path.resolve(
  process.env.ATLAS_E2E_ARTIFACT_DIR ?? path.resolve(process.cwd(), "../../var/populated-workspace"),
);
const apiDir = path.resolve(process.cwd(), "../api");
const python = path.join(apiDir, ".venv", "Scripts", "python.exe");

function prepare(...args: string[]): string {
  return execFileSync(
    python,
    ["-m", "app.scripts.prepare_populated_e2e", "--organization-slug", slug, ...args],
    {
      cwd: apiDir,
      env: { ...process.env, ATLAS_E2E_PRODUCTION: "1" },
      encoding: "utf8",
    },
  );
}

async function capture(page: import("@playwright/test").Page, name: string): Promise<void> {
  mkdirSync(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, name), fullPage: true });
}

test.beforeAll(() => {
  prepare();
  prepare("--verify");
});

test.afterAll(() => {
  prepare("--cleanup");
});

test("populated workspace supports connected CRM operations", async ({ page }) => {
  const consoleErrors: string[] = [];
  const failedResponses: Array<{ method: string; path: string; status: number; beforeAuth: boolean }> = [];
  let authenticated = false;
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() < 400) return;
    const url = new URL(response.url());
    failedResponses.push({
      method: response.request().method(),
      path: url.pathname,
      status: response.status(),
      beforeAuth: !authenticated,
    });
  });

  await signInAsSeedAdmin(page);
  authenticated = true;
  await page.getByLabel("Organization").selectOption({ label: "ATLAS Sample Workspace" });
  await expect(page.locator("#organization-selector option:checked")).toHaveText("ATLAS Sample Workspace");
  const metricValue = (label: string) =>
    page.getByRole("link", { name: new RegExp(label) }).locator("p").nth(1);
  await expect(metricValue("Active companies")).toHaveText("03");
  await expect(metricValue("Active leads")).toHaveText("03");
  await expect(metricValue("Open inquiries")).toHaveText("03");
  await capture(page, "populated-overview-desktop.png");

  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer records" })).toBeVisible();

  await page.getByRole("tab", { name: "Companies" }).click();
  await page.getByRole("button", { name: "Sample workspace · Harbor Freight", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sample workspace · Harbor Freight", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mina Patel", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sample workspace · North pier expansion", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Mina Patel", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Mina Patel", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sample workspace · North pier expansion", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sample workspace · North pier expansion", exact: true })).toBeVisible();
  const inquiry = page.getByRole("button", {
    name: "Sample workspace · Capacity for Q3 expansion",
    exact: true,
  });
  await expect(inquiry).toHaveCount(1);
  await inquiry.click();
  await expect(
    page.getByRole("heading", {
      name: "Sample workspace · Capacity for Q3 expansion",
      exact: true,
    }),
  ).toBeVisible();

  await page.getByRole("tab", { name: "Leads" }).click();
  await page.getByRole("button", { name: "Sample workspace · North pier expansion", exact: true }).click();
  await page.getByLabel("Status", { exact: true }).selectOption("won");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "Leads" }).click();
  await page.getByRole("button", { name: "Sample workspace · North pier expansion", exact: true }).click();
  await expect(page.getByLabel("Status", { exact: true })).toHaveValue("won");

  await page.getByRole("button", { name: "Archive" }).click();
  await page.getByRole("button", { name: "Confirm archive" }).click();
  await page.getByLabel("Show archived").uncheck();
  await expect(page.getByRole("button", { name: "Sample workspace · North pier expansion", exact: true })).toHaveCount(0);
  await page.getByLabel("Show archived").check();
  await page.getByRole("button", { name: "Sample workspace · North pier expansion", exact: true }).click();
  await page.getByRole("button", { name: "Restore" }).click();
  await page.getByLabel("Show archived").uncheck();
  await expect(page.getByRole("button", { name: "Sample workspace · North pier expansion", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "AI Assistant", exact: true }).click();
  const conversation = page.getByRole("button", {
    name: /^Sample workspace · Working with the sample pipeline/,
  });
  await expect(conversation).toHaveCount(1);
  await conversation.click();
  await expect(
    page.getByRole("heading", {
      name: "Sample workspace · Working with the sample pipeline",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("Summarize the active sample opportunities.", { exact: true })).toBeVisible();
  await capture(page, "populated-crm-desktop.png");
  const unexpectedResponses = failedResponses.filter((response) => {
    const expectedUnauthenticatedBootstrap =
      response.beforeAuth && response.status === 401 && response.path === "/api/v1/auth/me";
    const expectedMissingPrediction =
      response.status === 404 && /\/api\/v1\/organizations\/[^/]+\/leads\/[^/]+\/predictions$/.test(response.path);
    return !expectedUnauthenticatedBootstrap && !expectedMissingPrediction;
  });
  expect(unexpectedResponses, `Unexpected failed responses: ${JSON.stringify(failedResponses)}`).toEqual([]);
  expect(
    consoleErrors.filter((message) => !message.includes("401") && !message.includes("404")),
    `Unexpected browser console errors: ${JSON.stringify(consoleErrors)}`,
  ).toEqual([]);
});

test("populated workspace remains usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInAsSeedAdmin(page);
  await page.getByLabel("Organization").selectOption({ label: "ATLAS Sample Workspace" });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer records" })).toBeVisible();
  await capture(page, "populated-crm-mobile.png");
});
