import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

test("approved email is delivered once and visible in Email Activity", async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  const stamp = Date.now();
  const subject = `Email acceptance ${stamp}`;
  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await page.getByRole("tab", { name: "Inquiries" }).click();
  await page.getByRole("button", { name: "New inquiry" }).click();
  await page.getByLabel("Subject").fill(subject);
  await page.getByLabel("Body").fill("Mina Patel asked for a response about bonded storage.");
  await page.getByRole("button", { name: "Create" }).click();

  await page.getByRole("link", { name: "Agent Runs" }).click();
  await page.getByRole("button", { name: "Start from inquiry" }).click();
  await page.getByLabel("Inquiry").selectOption({ label: subject });
  const started = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/agent-runs") && response.ok(),
  );
  await page.getByRole("button", { name: "Start", exact: true }).click();
  const startedBody = await started.then((response) => response.json() as Promise<{
    approvals: { id: string; action_type: string }[];
  }>);
  const responseApproval = startedBody.approvals.find(
    (approval) => approval.action_type === "prepare_customer_response",
  );
  expect(responseApproval?.id).toBeTruthy();
  await expect(page.getByRole("cell", { name: "awaiting approval" }).first()).toBeVisible();

  await page.getByRole("link", { name: "Approvals", exact: true }).click();
  const pendingResponse = page.waitForResponse(
    (response) => response.request().method() === "GET" && response.url().includes("/approvals") && response.url().includes("status=pending") && response.ok(),
  );
  await page.getByLabel("Filter approvals").selectOption("pending");
  await pendingResponse;
  await page.locator(`[data-approval-id="${responseApproval?.id}"]`).click();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved. Execute writes the stored payload.")).toBeVisible();
  const approvedResponse = page.waitForResponse(
    (response) => response.request().method() === "GET" && response.url().includes("/approvals") && response.url().includes("status=approved") && response.ok(),
  );
  await page.getByLabel("Filter approvals").selectOption("approved");
  await approvedResponse;
  const approvalRow = page.locator(`[data-approval-id="${responseApproval?.id}"]`);
  await approvalRow.click();
  const execution = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/execute") && response.ok(),
  );
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Execute" }).click();
  const executionBody = await execution.then((response) => response.json() as Promise<{ status: string }>);
  expect(executionBody.status).toBe("executing");

  await page.getByRole("link", { name: "Workflows" }).click();
  await expect(page.getByRole("heading", { name: "Email activity" })).toBeVisible();
  const activityText = await page.locator("body").innerText();
  if (!activityText.includes("Accepted by SMTP")) {
    throw new Error(`Email activity did not reach SMTP acceptance: ${activityText.slice(-1200)}`);
  }
  await expect(page.getByText("Accepted by SMTP")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Mailpit sandbox")).toBeVisible();
  await page.screenshot({ path: path.resolve(process.cwd(), "../../var/email-activity-desktop.png"), fullPage: true });

  const httpPort = readFileSync(path.resolve(process.cwd(), "../../var/e2e-mailpit.http-port"), "utf8").trim();
  const messages = await request.get(`http://127.0.0.1:${httpPort}/api/v1/messages`);
  expect(messages.ok()).toBeTruthy();
  const body = await messages.json() as { messages: { To: { Address: string }[]; Subject: string }[] };
  expect(body.messages).toHaveLength(1);
  expect(body.messages[0]?.Subject).toContain(subject);

  await page.reload();
  await expect(page.getByText("Accepted by SMTP")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.resolve(process.cwd(), "../../var/email-activity-mobile.png"), fullPage: true });
});
