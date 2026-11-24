import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

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

  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Operations overview" })).toBeVisible();

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
  await page.getByLabel("Title").fill(lead);
  await page.getByLabel("Company").selectOption({ label: company });
  await page.getByLabel("Contact").selectOption({ label: contact });
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
  await page.getByLabel("Lead").selectOption({ label: lead });
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: inquiry })).toBeVisible();

  for (const tabName of ["Companies", "Contacts", "Leads", "Inquiries"]) {
    await page.getByRole("tab", { name: tabName }).click();
    await page.getByLabel("Show archived").check();
    await page.getByLabel("Search " + tabName.toLowerCase()).fill(
      tabName === "Companies" ? company : tabName === "Contacts" ? contact : tabName === "Leads" ? lead : inquiry,
    );
    const record = page.getByRole("button", { name: tabName === "Companies" ? company : tabName === "Contacts" ? contact : tabName === "Leads" ? lead : inquiry });
    await record.click();
    await page.getByRole("button", { name: "Archive" }).click();
    await page.getByRole("button", { name: "Confirm archive" }).click();
    await page.reload();
    await page.getByRole("link", { name: "CRM", exact: true }).click();
    await page.getByRole("tab", { name: tabName }).click();
    await page.getByLabel("Show archived").uncheck();
    await page.getByLabel("Search " + tabName.toLowerCase()).fill(
      tabName === "Companies" ? company : tabName === "Contacts" ? contact : tabName === "Leads" ? lead : inquiry,
    );
    await expect(record).toHaveCount(0);
    await page.getByLabel("Show archived").check();
    await page.getByRole("button", { name: tabName === "Companies" ? company : tabName === "Contacts" ? contact : tabName === "Leads" ? lead : inquiry }).click();
    await page.getByRole("button", { name: "Restore" }).click();
    await page.getByLabel("Show archived").uncheck();
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
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer records" })).toBeVisible();
  await screenshot(page, "crm-mobile.png");
});
