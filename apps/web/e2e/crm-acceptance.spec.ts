import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

const artifactDir = path.resolve(process.env.ATLAS_E2E_ARTIFACT_DIR ?? path.resolve(process.cwd(), "../../var/crm-browser-acceptance"));

async function screenshot(page: import("@playwright/test").Page, name: string): Promise<void> {
  mkdirSync(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, name), fullPage: true });
}

test("CRM lifecycle persists relationships and recoverable archives", async ({ page }) => {
  const stamp = Date.now().toString();
  const company = `Browser Company ${stamp}`;
  const contact = `Browser Contact ${stamp}`;
  const lead = `Browser Lead ${stamp}`;
  const inquiry = `Browser Inquiry ${stamp}`;

  await signInAsSeedAdmin(page);

  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await page.getByRole("button", { name: "New company" }).click();
  await page.getByLabel("Name").fill(company);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: company })).toBeVisible();
  await screenshot(page, "crm-desktop.png");

  await page.getByRole("tab", { name: "Contacts" }).click();
  await page.getByRole("button", { name: "New contact" }).click();
  await page.getByLabel("Name").fill(contact);
  await page.getByLabel("Company").selectOption({ label: company });
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: contact })).toBeVisible();

  await page.getByRole("tab", { name: "Leads" }).click();
  await page.getByRole("button", { name: "New lead" }).click();
  await page.locator("#lead-create-title").fill(lead);
  await page.getByLabel("Company").selectOption({ label: company });
  await page.locator("#lead-create-contact").selectOption({ label: contact });
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: lead })).toBeVisible();
  await page.getByLabel("Status", { exact: true }).selectOption("qualified");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.getByRole("tab", { name: "Inquiries" }).click();
  await page.getByRole("button", { name: "New inquiry" }).click();
  await page.getByLabel("Subject").fill(inquiry);
  await page.getByLabel("Body").fill("A browser-created inquiry.");
  await page.getByLabel("Company").selectOption({ label: company });
  await page.getByLabel("Lead", { exact: true }).selectOption({ label: lead });
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: inquiry })).toBeVisible();

  for (const tabName of ["Companies", "Contacts", "Leads", "Inquiries"]) {
    const tabId = tabName.toLowerCase();
    const recordName = tabName === "Companies" ? company : tabName === "Contacts" ? contact : tabName === "Leads" ? lead : inquiry;
    await page.getByRole("tab", { name: tabName }).click();
    await page.getByLabel("Show archived").check();
    await page.getByLabel("Search " + tabName.toLowerCase()).fill(
      recordName,
    );
    const record = page.getByRole("button", { name: recordName, exact: true });
    await record.click();
    await page.getByRole("button", { name: "Archive" }).click();
    const [archiveResponse] = await Promise.all([
      page.waitForResponse(
        (response) => response.request().method() === "DELETE" && response.url().includes(`/${tabId}/`) && response.ok(),
      ),
      page.getByRole("button", { name: "Confirm archive" }).click(),
    ]);
    expect(archiveResponse.ok()).toBe(true);
    await page.goto(`/crm?tab=${tabId}`);
    await expect(page.getByRole("tab", { name: tabName, exact: true })).toHaveAttribute("aria-selected", "true");
    const hiddenList = page.waitForResponse(
      (response) => response.request().method() === "GET" && response.url().includes(`/${tabId}`) && response.url().includes("q=") && response.ok(),
    );
    await page.getByLabel("Show archived").uncheck();
    await page.getByLabel("Search " + tabName.toLowerCase()).fill(recordName);
    await hiddenList;
    await expect(record).toHaveCount(0);
    const archivedList = page.waitForResponse(
      (response) => response.request().method() === "GET" && response.url().includes(`/${tabId}`) && response.url().includes("include_archived=true") && response.ok(),
    );
    await page.getByLabel("Show archived").check();
    await page.getByLabel("Search " + tabName.toLowerCase()).fill(recordName);
    await archivedList;
    await expect(record).toBeVisible();
    await record.click();
    const detail = page.getByTestId(`crm-detail-${tabId}`);
    await expect(detail, `${tabName} archived record detail did not open`).toBeVisible();
    const selectedId = new URL(page.url()).searchParams.get("id");
    expect(selectedId, `${tabName} selection id is missing`).toBeTruthy();
    await expect(detail, `${tabName} detail selected a different record`).toHaveAttribute("data-record-id", selectedId ?? "");
    await expect(detail, `${tabName} record is not archived in the detail response`).toHaveAttribute("data-archived", "true");
    await expect(detail.getByRole("heading", { name: recordName, exact: true })).toBeVisible();
    const [restoreResponse] = await Promise.all([
      page.waitForResponse(
        (response) => response.request().method() === "POST" && response.url().includes(`/restore`) && response.ok(),
      ),
      page.getByRole("button", { name: "Restore", exact: true }).click(),
    ]);
    expect(restoreResponse.ok()).toBe(true);
    await page.getByLabel("Show archived").uncheck();
    await page.getByLabel("Search " + tabName.toLowerCase()).fill(recordName);
    await expect(record).toBeVisible();
  }

  await page.reload();
  await expect(page.getByRole("heading", { name: "Customer records" })).toBeVisible();
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await page.getByRole("tab", { name: "Leads" }).click();
  await page.getByLabel("Search leads").fill(lead);
  await expect(page.getByRole("button", { name: lead })).toBeVisible();
  await screenshot(page, "crm-persisted-desktop.png");
});

test("CRM remains usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInAsSeedAdmin(page);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer records" })).toBeVisible();
  await screenshot(page, "crm-mobile.png");
});
