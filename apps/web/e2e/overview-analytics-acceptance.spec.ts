import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

const artifactDir = path.resolve(process.env.ATLAS_E2E_ARTIFACT_DIR ?? path.resolve(process.cwd(), "../../var/overview-analytics-browser"));

async function screenshot(page: import("@playwright/test").Page, name: string): Promise<void> {
  mkdirSync(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, name), fullPage: true });
}

async function metric(page: import("@playwright/test").Page, label: string): Promise<number> {
  const slug = label.toLowerCase().replaceAll(" ", "-");
  const overviewValue = page.getByTestId(`overview-kpi-${slug}-value`);
  const analyticsValue = page.getByTestId(`analytics-metric-${slug}-value`);
  const overviewCount = await overviewValue.count();
  const analyticsCount = await analyticsValue.count();
  if (overviewCount + analyticsCount !== 1) {
    throw new Error(`Metric ${label} must have exactly one page-specific value element; found Overview=${overviewCount}, Analytics=${analyticsCount}`);
  }
  const valueElement = overviewCount === 1 ? overviewValue : analyticsValue;
  await expect(valueElement).toBeVisible();
  const valueText = await valueElement.textContent();
  const value = Number.parseInt(valueText?.trim() ?? "", 10);
  if (!Number.isFinite(value)) throw new Error(`Metric ${label} did not render a numeric value: ${valueText ?? "<missing>"}`);
  return value;
}

async function waitForAnalytics(page: import("@playwright/test").Page, networkFailures: string[]): Promise<void> {
  // Fail with the actual API/network error rather than a misleading missing-metric timeout.
  await expect.poll(async () => {
    const alert = page.getByRole("main").getByRole("alert");
    if (await alert.count()) {
      const message = (await alert.first().textContent())?.trim() ?? "Unknown Analytics error";
      throw new Error(`Analytics could not load: ${message}\nNetwork diagnostics:\n${networkFailures.join("\n") || "No recorded request failures"}`);
    }
    return await page.getByTestId("analytics-metric-active-companies").isVisible();
  }, { message: "Analytics should render its metrics or report a real API error" }).toBe(true);
  await expect(page.getByTestId("analytics-metric-active-companies")).toBeVisible();
  await expect(page.getByTestId("analytics-metric-leads")).toBeVisible();
  await expect(page.getByTestId("analytics-metric-open-inquiries")).toBeVisible();
}

async function assertWorkspace(page: import("@playwright/test").Page): Promise<void> {
  await expect(page.getByRole("combobox", { name: "Organization" }).locator("option:checked")).toHaveText("Atlas Demo");
}

async function openOverview(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByTestId("overview-workspace")).toBeVisible();
  await assertWorkspace(page);
  await expect(page.getByTestId("overview-kpi-companies")).toBeVisible();
  await expect(page.getByTestId("overview-kpi-active-leads")).toBeVisible();
  await expect(page.getByTestId("overview-kpi-customer-requests")).toBeVisible();
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

  const networkFailures: string[] = [];
  page.on("requestfailed", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) {
      networkFailures.push(`FAILED ${request.method()} ${url.origin}${url.pathname}: ${request.failure()?.errorText ?? "unknown"}`);
    }
  });
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/") && !response.ok()) {
      networkFailures.push(`HTTP ${response.status()} ${response.request().method()} ${url.origin}${url.pathname}`);
    }
  });

  await signInAsSeedAdmin(page);
  await page.goto("/analytics");
  await assertWorkspace(page);
  await waitForAnalytics(page, networkFailures);
  await allRecords(page);
  const companiesBefore = await metric(page, "Active companies");
  const leadsBefore = await metric(page, "Leads");
  const inquiriesBefore = await metric(page, "Open inquiries");
  console.log(JSON.stringify({ metricsBefore: { companies: companiesBefore, leads: leadsBefore, openInquiries: inquiriesBefore } }));
  await openOverview(page);
  const activeLeadsBefore = await metric(page, "Active leads");
  console.log(JSON.stringify({ activeLeadsBefore }));
  await allRecords(page);
  await expect(page.getByRole("link", { name: /Companies/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent customer activity" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Lead pipeline" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Open inquiries" })).toBeVisible();
  await screenshot(page, "overview-before.png");

  await page.goto("/crm");
  await page.getByRole("button", { name: "New company" }).click();
  await page.getByLabel("Name").fill(company);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: company })).toBeVisible();

  await page.getByRole("tab", { name: "Leads" }).click();
  await page.getByRole("button", { name: "New lead" }).click();
  await page.locator("#lead-create-title").fill(lead);
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

  await openOverview(page);
  await allRecords(page);
  await expect.poll(() => metric(page, "Companies")).toBe(companiesBefore + 1);
  await expect.poll(() => metric(page, "Active leads")).toBe(activeLeadsBefore + 1);
  await expect.poll(() => metric(page, "Customer requests")).toBe(inquiriesBefore + 1);
  console.log(JSON.stringify({ metricsAfterCreate: { companies: companiesBefore + 1, totalLeads: leadsBefore + 1, activeLeads: activeLeadsBefore + 1, openInquiries: inquiriesBefore + 1 } }));

  await page.goto("/analytics");
  await assertWorkspace(page);
  await waitForAnalytics(page, networkFailures);
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
  await assertWorkspace(page);
  await waitForAnalytics(page, networkFailures);
  await allRecords(page);
  const pipeline = page.locator("section").filter({ has: page.getByRole("heading", { name: "Lead pipeline" }) });
  await expect(pipeline.getByText("qualified", { exact: true })).toBeVisible();
  await screenshot(page, "analytics-after-stage.png");

  await openOverview(page);
  await allRecords(page);
  await page.getByRole("link", { name: /Companies/ }).click();
  await expect(page).toHaveURL(/\/crm\?tab=companies/);
  await page.getByLabel("Search companies").fill(company);
  await expect(page.getByRole("button", { name: company })).toBeVisible();
  await openOverview(page);
  await allRecords(page);
  await page.getByRole("link", { name: "Active leads" }).click();
  await expect(page).toHaveURL(/\/crm\?tab=leads/);
  await page.getByLabel("Search leads").fill(lead);
  await expect(page.getByRole("button", { name: lead })).toBeVisible();

  await page.getByRole("button", { name: lead }).click();
  await page.getByRole("button", { name: "Archive" }).click();
  await page.getByRole("button", { name: "Confirm archive" }).click();
  await openOverview(page);
  await allRecords(page);
  await expect.poll(() => metric(page, "Active leads")).toBe(activeLeadsBefore);
  console.log(JSON.stringify({ metricsAfterArchive: { activeLeads: activeLeadsBefore } }));
  await page.getByRole("link", { name: "Active leads" }).click();
  await page.getByLabel("Show archived").check();
  await page.getByLabel("Search leads").fill(lead);
  await page.getByRole("button", { name: lead }).click();
  await page.getByRole("button", { name: "Restore" }).click();

  await openOverview(page);
  await expect.poll(() => metric(page, "Active leads")).toBe(activeLeadsBefore + 1);
  await page.reload();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByTestId("overview-workspace")).toBeVisible();
  await expect(page.getByTestId("overview-kpi-active-leads")).toBeVisible();
  await expect.poll(() => metric(page, "Active leads")).toBe(activeLeadsBefore + 1);
  console.log(JSON.stringify({ metricsAfterRestore: { activeLeads: activeLeadsBefore + 1 } }));
  await screenshot(page, "overview-after-restore.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot(page, "overview-mobile.png");
});
