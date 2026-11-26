import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const artifactDir = path.resolve(process.cwd(), "../../docs/demo/harbor");

async function shot(page: Page, name: string): Promise<void> {
  mkdirSync(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, name), fullPage: true });
}

test("Harbor demonstration supports the main workspace actions", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto("/demo");
  const launch = page.getByRole("main").getByRole("button", { name: "Launch interactive demo" }).first();
  await expect(launch).toBeEnabled({ timeout: 30_000 });
  await launch.click();
  await page.waitForURL(/\/overview/);
  await expect(page.getByTestId("overview-kpi-companies-value")).toHaveText("20", { timeout: 60_000 });
  await shot(page, "01-overview.png");

  await page.getByRole("link", { name: "Analytics", exact: true }).click();
  await page.getByLabel("Analytics date range").selectOption("90d");
  await expect(page.getByTestId("analytics-metric-active-companies-value")).toHaveText("20");
  await expect(page.getByTestId("analytics-metric-leads-value")).toHaveText("50");
  await shot(page, "09-analytics.png");

  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await page.getByLabel("Search companies").fill("Harbor");
  await page.getByRole("button", { name: "Harbor & Co.", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Harbor & Co.", exact: true })).toBeVisible();
  await expect(page.getByText("Mina Patel")).toBeVisible();
  const stamp = Date.now().toString();
  const company = `Session Yard ${stamp}`;
  await page.getByRole("button", { name: "New company" }).click();
  await page.getByRole("dialog", { name: "New company" }).getByLabel("Name").fill(company);
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByLabel("Search companies").fill(company);
  await expect(page.getByRole("button", { name: company, exact: true })).toBeVisible();
  await shot(page, "02-crm.png");

  await page.getByRole("link", { name: "Inbox", exact: true }).click();
  await page.getByLabel("Search inbox").fill("Cold storage");
  await page.getByRole("button", { name: /Cold storage for the north pier/ }).click();
  await expect(page.getByText("Could you confirm bonded and cold storage at the north pier yard?")).toBeVisible();
  await shot(page, "03-inbox.png");

  await page.getByRole("link", { name: "Knowledge", exact: true }).click();
  await expect(page.getByText("Bonded warehousing overview")).toBeVisible();
  await page.getByRole("button", { name: "Semantic search" }).click();
  await page.getByLabel("Search documents").fill("cold storage");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(/excerpt/)).toBeVisible();
  await shot(page, "04-knowledge.png");

  await page.getByRole("link", { name: "AI Assistant", exact: true }).click();
  await page.getByRole("button", { name: /Bonded yard capacity/ }).click();
  await page.getByLabel("Message to ATLAS").fill("Is bonded warehousing available at the north pier?");
  await page.getByRole("button", { name: "Send →" }).click();
  await expect(
    page.locator("article").filter({ hasText: "Demonstration assistant" }).last(),
  ).toContainText("Bonded warehousing is available at the north pier yard.");
  await shot(page, "05-assistant.png");

  await page.getByRole("link", { name: "Approvals", exact: true }).click();
  const decisionFilter = page.getByLabel("Filter loaded decisions");
  await decisionFilter.fill("Bonded warehousing");
  await page.getByRole("button", { name: /Prepare customer response/ }).click();
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByText("Rejected. No CRM change or external action was written.")).toBeVisible();
  await decisionFilter.fill("Cold storage rates");
  await page.getByRole("button", { name: /Prepare customer response/ }).click();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Execute", exact: true }).click();
  await expect(page.getByText("Demo sessions cannot send messages or call a live provider.")).toBeVisible();
  await decisionFilter.fill("Yard visit confirmed");
  await page.getByRole("button", { name: /Update lead/ }).click();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Execute", exact: true }).click();
  await expect(page.getByText("Executed. The stored result is on this approval.")).toBeVisible();
  await shot(page, "06-approvals.png");

  await page.goto("/crm?tab=leads");
  await page.getByLabel("Search leads").fill("North pier expansion");
  await page.getByRole("button", { name: "North pier expansion", exact: true }).click();
  await expect(page.getByTestId("crm-detail-leads").getByLabel("Notes")).toHaveValue(/Yard visit confirmed in this demonstration/);

  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByLabel("Search workflows").fill("Qualified lead");
  await page.getByRole("button", { name: /Qualified lead follow-up/ }).click();
  await page.getByRole("button", { name: "Runs and approvals" }).click();
  await expect(page.getByText("Followed the otherwise path.")).toBeVisible();
  await page.getByRole("button", { name: "Test workflow" }).click();
  await page.getByLabel("Lead").selectOption({ label: "North pier expansion" });
  await page.getByRole("button", { name: "Preview path" }).click();
  await expect(page.getByText("Preview only. No task, lead change, or follow-up draft was saved.")).toBeVisible();
  await shot(page, "07-workflows.png");

  await page.getByRole("link", { name: "Campaigns", exact: true }).click();
  await page.getByRole("button", { name: /Yard safety bulletin/ }).click();
  await expect(page.getByText("Simulated — not sent")).toBeVisible();
  await shot(page, "08-campaigns.png");
});
