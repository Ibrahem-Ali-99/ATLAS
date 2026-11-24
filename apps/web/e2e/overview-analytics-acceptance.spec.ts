import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const artifactDir = path.resolve(process.env.ATLAS_E2E_ARTIFACT_DIR ?? path.resolve(process.cwd(), "../../var/overview-analytics-browser"));

async function screenshot(page: import("@playwright/test").Page, name: string): Promise<void> {
  mkdirSync(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, name), fullPage: true });
}

async function metric(page: import("@playwright/test").Page, label: string): Promise<number> {
  const heading = page.getByText(label, { exact: true }).first();
  if (await heading.count() === 0) {
    return 0;
  }
  const card = heading.locator("..");
  const value = await card.locator("p").nth(1).textContent();
  return Number.parseInt(value?.trim() ?? "0", 10);
}

async function signIn(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Operations overview" })).toBeVisible();
}

async function allRecords(page: import("@playwright/test").Page): Promise<void> {
  const button = page.getByRole("button", { name: "All records", exact: true });
  if (await button.count() > 0) {
    await expect(button).toBeVisible();
    await button.click();
    await expect(button).toHaveAttribute("aria-pressed", "true");
  }
}

test("Overview and Analytics follow CRM changes", async ({ page }) => {
  const stamp = Date.now().toString();
  const company = `Metrics Company ${stamp}`;
  const lead = `Metrics Lead ${stamp}`;
  const inquiry = `Metrics Inquiry ${stamp}`;

  await signIn(page);
  await page.goto("/analytics");
  await allRecords(page);
  const companiesBefore = await metric(page, "Active companies");
  const leadsBefore = await metric(page, "Leads");
  const inquiriesBefore = await metric(page, "Open inquiries");
  console.log(JSON.stringify({ metricsBefore: { companies: companiesBefore, leads: leadsBefore, openInquiries: inquiriesBefore } }));
  await page.goto("/overview");
  await allRecords(page);
  await expect(page.getByRole("link", { name: "Active companies" })).toBeVisible();
  await screenshot(page, "overview-before.png");

  await page.goto("/crm");
  await page.getByRole("button", { name: "New company" }).click();
  await page.getByLabel("Name").fill(company);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: company })).toBeVisible();

  await page.getByRole("tab", { name: "Leads" }).click();
  await page.getByRole("button", { name: "New lead" }).click();
  await page.getByLabel("Title").fill(lead);
  await page.getByLabel("Company").selectOption({ label: company });
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: lead })).toBeVisible();

  await page.getByRole("tab", { name: "Inquiries" }).click();
  await page.getByRole("button", { name: "New inquiry" }).click();
  await page.getByLabel("Subject").fill(inquiry);
  await page.getByLabel("Body").fill("A metrics acceptance inquiry.");
  await page.getByLabel("Company").selectOption({ label: company });
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: inquiry })).toBeVisible();

  await page.goto("/overview");
  await allRecords(page);
  await expect.poll(() => metric(page, "Active companies")).toBe(companiesBefore + 1);
  await expect.poll(() => metric(page, "Active leads")).toBe(leadsBefore + 1);
  await expect.poll(() => metric(page, "Open inquiries")).toBe(inquiriesBefore + 1);
  console.log(JSON.stringify({ metricsAfterCreate: { companies: companiesBefore + 1, leads: leadsBefore + 1, openInquiries: inquiriesBefore + 1 } }));

  await page.goto("/analytics");
  await allRecords(page);
  await expect(page.getByRole("heading", { name: "Lead pipeline" })).toBeVisible();
  await expect(page.getByText("new", { exact: true })).toBeVisible();
  await page.goto("/crm");
  await page.getByRole("tab", { name: "Leads" }).click();
  await page.getByRole("button", { name: lead }).click();
  await page.getByLabel("Status", { exact: true }).selectOption("qualified");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.goto("/analytics");
  await allRecords(page);
  const pipeline = page.locator("section").filter({ has: page.getByRole("heading", { name: "Lead pipeline" }) });
  await expect(pipeline.getByText("qualified", { exact: true })).toBeVisible();
  await screenshot(page, "analytics-after-stage.png");

  await page.goto("/overview");
  await allRecords(page);
  await page.getByRole("link", { name: "Active companies" }).click();
  await expect(page).toHaveURL(/\/crm\?tab=companies/);
  await page.getByLabel("Search companies").fill(company);
  await expect(page.getByRole("button", { name: company })).toBeVisible();
  await page.goto("/overview");
  await allRecords(page);
  await page.getByRole("link", { name: "Active leads" }).click();
  await expect(page).toHaveURL(/\/crm\?tab=leads/);
  await page.getByLabel("Search leads").fill(lead);
  await expect(page.getByRole("button", { name: lead })).toBeVisible();

  await page.getByRole("button", { name: lead }).click();
  await page.getByRole("button", { name: "Archive" }).click();
  await page.getByRole("button", { name: "Confirm archive" }).click();
  await page.goto("/overview");
  await allRecords(page);
  await expect.poll(() => metric(page, "Active leads")).toBe(leadsBefore);
  console.log(JSON.stringify({ metricsAfterArchive: { activeLeads: leadsBefore } }));
  await page.getByRole("link", { name: "Active leads" }).click();
  await page.getByLabel("Show archived").check();
  await page.getByLabel("Search leads").fill(lead);
  await page.getByRole("button", { name: lead }).click();
  await page.getByRole("button", { name: "Restore" }).click();

  await page.goto("/overview");
  await expect.poll(() => metric(page, "Active leads")).toBe(leadsBefore + 1);
  await page.reload();
  await expect.poll(() => metric(page, "Active leads")).toBe(leadsBefore + 1);
  console.log(JSON.stringify({ metricsAfterRestore: { activeLeads: leadsBefore + 1 } }));
  await screenshot(page, "overview-after-restore.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot(page, "overview-mobile.png");
});
