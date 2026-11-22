import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const shotDir = path.resolve(process.cwd(), "../../docs/demo/screenshots");

async function shot(page: Page, name: string): Promise<void> {
  mkdirSync(shotDir, { recursive: true });
  await page.screenshot({ path: path.join(shotDir, name), fullPage: true });
}

const stamp = Date.now().toString();
const companyName = `E2E Harbor ${stamp}`;
const leadTitle = `E2E pier ${stamp}`;
const documentTitle = `e2e-harbor-${stamp}`;

test("workspace flow uses the browser and deterministic providers", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Pending approvals")).toBeVisible();
  await shot(page, "01-overview.png");

  await page.getByRole("link", { name: "CRM" }).click();
  await page.getByRole("button", { name: "New company" }).click();
  await page.getByLabel("Name").fill(companyName);
  await page.getByLabel("Industry").fill("Logistics");
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByLabel("Search companies").fill(companyName);
  await expect(page.getByRole("button", { name: companyName })).toBeVisible();

  await page.getByRole("tab", { name: "Leads" }).click();
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
  await page.getByPlaceholder("Ask about a document or a CRM record").fill(`bonded-yard-${stamp}`);
  await page.getByRole("button", { name: "Send" }).click();
  const answer = page.getByRole("article").filter({ hasText: "Company documents" });
  await expect(answer.getByText("Grounded answer from the supplied company records.")).toBeVisible();
  await expect(answer.getByText(documentTitle)).toBeVisible();
  await shot(page, "04-assistant.png");

  await page.getByRole("link", { name: "CRM" }).click();
  await page.getByRole("tab", { name: "Inquiries" }).click();
  await page.getByRole("button", { name: "New inquiry" }).click();
  await page.getByLabel("Subject").fill(`Bonded storage ${stamp}`);
  await page.getByLabel("Body").fill("Mina Patel asked about bonded storage rates.");
  await page.getByRole("button", { name: "Create" }).click();

  await page.getByRole("link", { name: "Agent Runs" }).click();
  await page.getByRole("button", { name: "Start from inquiry" }).click();
  await page.getByLabel("Inquiry").selectOption({ label: `Bonded storage ${stamp}` });
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByRole("cell", { name: "awaiting approval" }).first()).toBeVisible();
  await shot(page, "05-agent-runs.png");

  await page.getByRole("link", { name: "Approvals" }).click();
  await page.getByRole("button", { name: /lead/ }).first().click();
  await page.getByRole("button", { name: "Approve" }).click();
  await page.getByLabel("Filter approvals").selectOption("approved");
  await page.getByRole("button", { name: /lead/ }).first().click();
  const executed = page.waitForResponse(
    (response) =>
      response.url().includes("/execute") && response.request().method() === "POST" && response.ok(),
  );
  await page.getByRole("button", { name: "Execute" }).click();
  await executed;
  await page.getByLabel("Filter approvals").selectOption("executed");
  await expect(page.getByRole("button", { name: "update lead" }).first()).toBeVisible();
  await page.getByRole("link", { name: "CRM" }).click();
  await page.getByRole("tab", { name: "Leads" }).click();
  await page.getByRole("button", { name: "North pier expansion" }).click();
  await expect(page.getByLabel("Notes")).toHaveValue("Rates for bonded storage");
  await shot(page, "06-crm-lead.png");

  await page.getByRole("link", { name: "Workflows" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await expect(page.getByText("sandbox", { exact: false }).first()).toBeVisible();
  await shot(page, "07-workflows.png");
  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
  await shot(page, "08-analytics.png");
  await page.getByRole("link", { name: "Monitoring" }).click();
  await expect(page.getByRole("heading", { name: "Monitoring" })).toBeVisible();
  await shot(page, "09-monitoring.png");

  await page.getByRole("link", { name: "Approvals" }).click();
  await page.getByLabel("Filter approvals").selectOption("pending");
  await page.getByRole("button", { name: /customer response/ }).first().click();
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
});
