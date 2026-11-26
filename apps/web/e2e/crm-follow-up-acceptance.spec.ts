import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";
import { sandboxEmailSubjects } from "./sandbox-mail";

test("grounded knowledge, CRM follow-up, approval and sandbox delivery work together", async ({ page }) => {
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
    if (url.pathname.startsWith("/api/") && request.failure()?.errorText !== "net::ERR_ABORTED") {
      failedRequests.push(`FAILED ${request.method()} ${url.origin}${url.pathname}: ${request.failure()?.errorText ?? "unknown"}`);
    }
  });
  page.on("pageerror", (error) => unexpectedResponses.push(`PAGEERROR ${error.message}`));

  await signInAsSeedAdmin(page);
  authenticated = true;
  const recipient = "mina.patel@harbor.example";
  const deliveriesBefore = (await sandboxEmailSubjects(page.request, recipient)).length;
  const subject = `Cold storage inquiry ${Date.now()}`;
  await page.goto("/crm?tab=inquiries");
  await page.getByRole("button", { name: "New inquiry" }).click();
  const intake = page.getByRole("dialog", { name: "New inquiry" });
  await intake.getByLabel("Subject").fill(subject);
  await intake.getByLabel("Body").fill("Can you confirm cold storage capacity for our delivery?");
  await intake.getByLabel("Lead").selectOption({ label: "North pier expansion" });
  await intake.getByRole("button", { name: "Create", exact: true }).click();
  const inquiry = page.getByTestId("crm-detail-inquiries");
  await expect(inquiry.getByRole("heading", { name: subject })).toBeVisible();
  const inquiryUrl = page.url();
  const document = `Capacity guide ${Date.now()}`;
  const reference = `capacity-reference-${Date.now()}`;
  await page.goto("/knowledge");
  await page.getByRole("button", { name: "Upload document" }).click();
  await page.getByLabel("Choose a PDF or TXT file").setInputFiles({
    name: `${document}.txt`, mimeType: "text/plain", buffer: Buffer.from(`Cold storage capacity reference is ${reference}.`),
  });
  await page.getByRole("button", { name: "Upload and index" }).click();
  await expect(page.getByRole("row", { name: document }).getByRole("cell", { name: "ready" })).toBeVisible({ timeout: 30_000 });
  await page.goto("/assistant");
  await page.getByRole("textbox", { name: "Message to ATLAS" }).fill(reference);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("article").getByText(document, { exact: true })).toBeVisible();
  await page.goto(inquiryUrl);
  await inquiry.getByRole("button", { name: "North pier expansion", exact: true }).click();
  await expect(page.getByText("Lead detail", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "North pier expansion", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Draft follow-up", exact: true }).click();

  await expect(page).toHaveURL(/\/agent-runs\?run=/);
  const runUrl = page.url();
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
  await expect(page.locator("main p").filter({ hasText: /^executed$/i })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main p").filter({ hasText: /sandbox email [0-9a-f-]{36}/i })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Approval details" }).getByText("executed", { exact: true })).toBeVisible();

  await expect.poll(async () => (await sandboxEmailSubjects(page.request, recipient)).length).toBe(deliveriesBefore + 1);
  await page.goto("/analytics");
  await expect.poll(async () => Number(await page.getByTestId("analytics-metric-delivery-value").textContent())).toBeGreaterThan(0);
  await page.getByText("View daily counts", { exact: true }).click();
  await expect(page.getByRole("table", { name: "Daily customer activity" })).toBeVisible();
  await page.goto(runUrl);
  const deliveryEvent = page.getByRole("listitem").filter({ hasText: "external effect" });
  await expect(deliveryEvent).toContainText("succeeded");

  expect([...unexpectedResponses, ...failedRequests]).toEqual([]);
});
