import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

const slug = `sample-follow-up-${process.pid}-${Date.now()}`;
const apiDir = path.resolve(process.cwd(), "../api");
const python = path.join(apiDir, ".venv", "Scripts", "python.exe");

function prepare(...args: string[]): void {
  execFileSync(
    python,
    ["-m", "app.scripts.prepare_populated_e2e", "--organization-slug", slug, ...args],
    { cwd: apiDir, env: { ...process.env, ATLAS_E2E_PRODUCTION: "1" } },
  );
}

test.beforeAll(() => prepare());
test.afterAll(() => prepare("--cleanup"));

test("CRM lead can produce and execute an approved sandbox follow-up", async ({ page }) => {
  let authenticated = false;
  const unexpectedResponses: string[] = [];
  const failedRequests: string[] = [];
  const isExpectedResponse = (status: number, pathname: string): boolean => {
    if (!authenticated && status === 401 && pathname === "/api/v1/auth/me") return true;
    return status === 404 && /^\/api\/v1\/organizations\/[^/]+\/leads\/[^/]+\/predictions$/.test(pathname);
  };
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/") && !response.ok() && !isExpectedResponse(response.status(), url.pathname)) {
      unexpectedResponses.push(`${response.status()} ${response.request().method()} ${url.origin}${url.pathname}`);
    }
  });
  page.on("requestfailed", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) {
      failedRequests.push(`FAILED ${request.method()} ${url.origin}${url.pathname}: ${request.failure()?.errorText ?? "unknown"}`);
    }
  });
  page.on("pageerror", (error) => unexpectedResponses.push(`PAGEERROR ${error.message}`));

  await signInAsSeedAdmin(page);
  authenticated = true;
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await page.getByRole("tab", { name: "Leads", exact: true }).click();

  const lead = page.getByRole("button", { name: "North pier expansion", exact: true });
  await expect(lead).toBeVisible();
  await lead.click();
  await expect(page.getByText("Lead detail", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "North pier expansion", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Draft follow-up", exact: true }).click();

  await expect(page).toHaveURL(/\/agent-runs\?run=/);
  await expect(page.locator("main").getByText("awaiting approval", { exact: true })).toBeVisible();
  await page
    .locator("article")
    .filter({ hasText: "Prepare customer response" })
    .getByRole("link", { name: "Review proposal", exact: true })
    .click();
  await expect(page).toHaveURL(/\/approvals\?approval=/);
  await expect(page.getByRole("heading", { name: "Prepare customer response", exact: true })).toBeVisible();
  await expect(page.getByText("Sandbox email", { exact: true })).toBeVisible();
  await expect(page.getByText("Affected:", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.locator("main p").filter({ hasText: /^approved$/i })).toBeVisible();
  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("confirm");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Execute", exact: true }).click();
  await expect(page.locator("main p").filter({ hasText: /^executing$/i })).toBeVisible();
  await expect(page.locator("main p").filter({ hasText: /^executed$/i })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main p").filter({ hasText: /sandbox email [0-9a-f-]{36}/i })).toBeVisible();

  expect([...unexpectedResponses, ...failedRequests]).toEqual([]);
});
