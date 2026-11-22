import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page, type Response } from "@playwright/test";

import { isStaleChunkError } from "../src/lib/chunk-error";

test("a missing JavaScript chunk is recognized as a stale bundle", () => {
  expect(
    isStaleChunkError(new Error("Failed to load chunk /_next/static/chunks/1nydp4gkw8786.js from module 64893")),
  ).toBe(true);
  expect(isStaleChunkError(new Error("Resource not found"))).toBe(false);
});

const shotDir = path.resolve(process.cwd(), "../../docs/demo/screenshots");

async function shot(page: Page, name: string): Promise<void> {
  mkdirSync(shotDir, { recursive: true });
  await page.screenshot({ path: path.join(shotDir, name), fullPage: true });
}

type LeadRow = { id: string; title: string; notes: string | null };
type ApprovalRow = {
  id: string;
  run_id: string;
  action_type: string;
  payload: { lead_id?: string; notes?: string };
  execution_result?: { lead_id?: string } | null;
  status?: string;
};

async function jsonBody<T>(response: Response): Promise<T> {
  return response.json() as Promise<T>;
}

async function selectApproval(page: Page, approvalId: string, items: ApprovalRow[]): Promise<void> {
  const index = items.findIndex((item) => item.id === approvalId);
  expect(index, approvalId).toBeGreaterThanOrEqual(0);
  const button = page.locator("section").first().getByRole("button").nth(index);
  await expect(button).toBeVisible();
  await button.click();
}

const stamp = Date.now().toString();
const companyName = `E2E Harbor ${stamp}`;
const leadTitle = `E2E pier ${stamp}`;
const documentTitle = `e2e-harbor-${stamp}`;

test("workspace flow uses the browser and deterministic providers", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const failedChunks: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/_next/static/chunks/") && response.status() >= 400) {
      failedChunks.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Pending approvals")).toBeVisible();
  await shot(page, "01-overview.png");

  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await page.getByRole("button", { name: "New company" }).click();
  await page.getByLabel("Name").fill(companyName);
  await page.getByLabel("Industry").fill("Logistics");
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByLabel("Search companies").fill(companyName);
  await expect(page.getByRole("button", { name: companyName })).toBeVisible();

  await page.getByRole("tab", { name: "Leads" }).click();
  const seededLeads = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes("/leads") &&
      response.url().includes("q=North") &&
      response.ok(),
  );
  await page.getByLabel("Search leads").fill("North pier expansion");
  const seeded = await jsonBody<{ items: LeadRow[] }>(await seededLeads);
  const northPier = seeded.items.find((item) => item.title === "North pier expansion");
  expect(northPier).toBeTruthy();
  const northPierId = northPier?.id ?? "";
  await page.getByLabel("Search leads").fill("");
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "New lead" }).click();
  await page.getByLabel("Title").fill(leadTitle);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: leadTitle })).toBeVisible();
  await shot(page, "02-crm.png");

  await page.getByRole("link", { name: "Knowledge" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: `${documentTitle}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`Harbor warehousing includes cold storage and bonded-yard-${stamp}.`),
  });
  const documentRow = page.getByRole("row", { name: documentTitle });
  await expect(documentRow).toBeVisible();
  await expect(documentRow.getByRole("cell", { name: "ready" })).toBeVisible({ timeout: 30_000 });
  await shot(page, "03-knowledge.png");

  await page.getByRole("link", { name: "AI Assistant" }).click();
  await page.getByRole("button", { name: "New" }).click();
  await page.getByPlaceholder("Ask about records, documents or your organization…").fill(`bonded-yard-${stamp}`);
  await page.getByRole("button", { name: "Send" }).click();
  const answer = page.getByRole("article").filter({ hasText: "Grounded answer from the supplied company records." });
  await expect(answer.getByText("Grounded answer from the supplied company records.")).toBeVisible();
  await expect(answer.getByText(documentTitle)).toBeVisible();
  await shot(page, "04-assistant.png");

  await page.getByPlaceholder("Ask about records, documents or your organization…").fill("What can you help me with?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("heading", { name: "What I can help with" })).toBeVisible();
  await expect(page.getByText("I could not find relevant company documents or CRM records for that question.")).toHaveCount(0);

  await page.getByPlaceholder("Ask about records, documents or your organization…").fill("Which companies are in my CRM?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("heading", { name: "Companies in this organization" })).toBeVisible();

  await page.getByPlaceholder("Ask about records, documents or your organization…").fill("What does the document you mentioned say?");
  await page.getByRole("button", { name: "Send" }).click();
  const followUp = page.getByRole("article").filter({ hasText: documentTitle });
  await expect(followUp.getByText("Grounded answer from the supplied company records.")).toHaveCount(2);

  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await page.getByRole("tab", { name: "Inquiries" }).click();
  await page.getByRole("button", { name: "New inquiry" }).click();
  await page.getByLabel("Subject").fill(`Bonded storage ${stamp}`);
  await page.getByLabel("Body").fill("Mina Patel asked about bonded storage rates.");
  await page.getByRole("button", { name: "Create" }).click();

  await page.getByRole("link", { name: "Agent Runs" }).click();
  await page.getByRole("button", { name: "Start from inquiry" }).click();
  await page.getByLabel("Inquiry").selectOption({ label: `Bonded storage ${stamp}` });
  const started = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/agent-runs") &&
      response.ok(),
  );
  await page.getByRole("button", { name: "Start", exact: true }).click();
  const startedBody = await jsonBody<{ run: { id: string }; approvals: ApprovalRow[] }>(await started);
  const runId = startedBody.run.id;
  const leadApproval = startedBody.approvals.find((item) => item.action_type === "update_lead");
  const responseApproval = startedBody.approvals.find(
    (item) => item.action_type === "prepare_customer_response",
  );
  expect(leadApproval?.run_id).toBe(runId);
  expect(leadApproval?.payload.lead_id).toBe(northPierId);
  expect(leadApproval?.payload.notes).toBe("Rates for bonded storage");
  expect(responseApproval?.run_id).toBe(runId);
  await expect(page.getByRole("cell", { name: "awaiting approval" }).first()).toBeVisible();
  await shot(page, "05-agent-runs.png");

  const pendingApprovals = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes("/approvals") &&
      response.url().includes("status=pending") &&
      response.ok(),
  );
  await page.getByRole("link", { name: "Approvals", exact: true }).click();
  const pending = await jsonBody<{ items: ApprovalRow[] }>(await pendingApprovals);
  await selectApproval(page, leadApproval?.id ?? "", pending.items);
  const leadProposal = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "update lead" }) })
    .locator("pre");
  await expect(leadProposal).toContainText(northPierId);
  await expect(leadProposal).toContainText("Rates for bonded storage");
  await page.getByRole("button", { name: "Approve" }).click();
  const approvedApprovals = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes("/approvals") &&
      response.url().includes("status=approved") &&
      response.ok(),
  );
  await page.getByLabel("Filter approvals").selectOption("approved");
  const approved = await jsonBody<{ items: ApprovalRow[] }>(await approvedApprovals);
  await selectApproval(page, leadApproval?.id ?? "", approved.items);
  const executed = page.waitForResponse(
    (response) =>
      response.url().includes(`/approvals/${leadApproval?.id}/execute`) &&
      response.request().method() === "POST" &&
      response.ok(),
  );
  await page.getByRole("button", { name: "Execute" }).click();
  const executedBody = await jsonBody<ApprovalRow>(await executed);
  expect(executedBody.status).toBe("executed");
  expect(executedBody.execution_result?.lead_id).toBe(northPierId);
  await page.getByLabel("Filter approvals").selectOption("executed");
  await expect(page.getByRole("button", { name: "update lead" }).first()).toBeVisible();
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await page.getByRole("tab", { name: "Leads" }).click();
  const refreshedLeads = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes("/leads") &&
      response.url().includes("q=North") &&
      response.ok(),
  );
  await page.getByLabel("Search leads").fill("North pier expansion");
  const refreshed = await jsonBody<{ items: LeadRow[] }>(await refreshedLeads);
  const updated = refreshed.items.find((item) => item.id === northPierId);
  expect(updated?.notes).toBe("Rates for bonded storage");
  await page.getByRole("button", { name: "North pier expansion" }).click();
  await expect(page.getByLabel("Notes")).toHaveValue("Rates for bonded storage");
  await shot(page, "06-crm-lead.png");

  await page.getByRole("link", { name: "Workflows" }).click();
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expect(page.getByText("sandbox", { exact: false }).first()).toBeVisible();
  await shot(page, "07-workflows.png");
  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
  await shot(page, "08-analytics.png");
  await page.getByRole("link", { name: "Monitoring" }).click();
  await expect(page.getByRole("heading", { name: "Monitoring" })).toBeVisible();
  await shot(page, "09-monitoring.png");

  const pendingResponses = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes("/approvals") &&
      response.url().includes("status=pending") &&
      response.ok(),
  );
  await page.getByRole("link", { name: "Approvals", exact: true }).click();
  await page.getByLabel("Filter approvals").selectOption("pending");
  const pendingAgain = await jsonBody<{ items: ApprovalRow[] }>(await pendingResponses);
  await selectApproval(page, responseApproval?.id ?? "", pendingAgain.items);
  await expect(
    page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "prepare customer response" }) })
      .locator("pre"),
  ).toContainText("We can discuss bonded storage.");
  await page.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByText("Rejected. No CRM change or external action was written.")).toBeVisible();
  await page.getByLabel("Filter approvals").selectOption("rejected");
  await expect(page.getByRole("button", { name: /customer response/ }).first()).toBeVisible();
  await shot(page, "11-approval-rejected.png");

  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByLabel("Name")).toHaveValue("Avery Admin");
  await shot(page, "10-settings.png");

  await page.getByRole("button", { name: /Avery Admin/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect(failedChunks).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test("narrow viewport opens every page without a missing chunk", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const failedChunks: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/_next/static/chunks/") && response.status() >= 400) {
      failedChunks.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await shot(page, "12-overview-mobile.png");
  const pages: [string, string][] = [
    ["CRM", "/crm"],
    ["Knowledge", "/knowledge"],
    ["AI Assistant", "/assistant"],
    ["Agent Runs", "/agent-runs"],
    ["Approvals", "/approvals"],
    ["Workflows", "/workflows"],
    ["Analytics", "/analytics"],
    ["Monitoring", "/monitoring"],
    ["Settings", "/settings"],
  ];
  for (const [name, href] of pages) {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await page.getByRole("link", { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${href}$`));
    await expect(page.locator("header").getByText(name, { exact: true })).toBeVisible();
    await expect(page.getByText("This page failed to render")).toHaveCount(0);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  }
  await shot(page, "13-approvals-mobile.png");
  for (const size of [
    { width: 1920, height: 1080 },
    { width: 768, height: 1024 },
  ]) {
    await page.setViewportSize(size);
    await page.goto("/overview");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/approvals");
  await page.reload();
  await expect(page.getByLabel("Filter approvals")).toBeVisible();
  expect(failedChunks).toEqual([]);
  expect(pageErrors).toEqual([]);
});
