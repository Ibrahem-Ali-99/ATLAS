import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";
import { sandboxEmailSubjects } from "./sandbox-mail";

test("approved email is delivered once and visible in Email Activity", async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signInAsSeedAdmin(page);
  const expectedSubject = "Bonded storage inquiry";
  const recipient = "mina.patel@harbor.example";
  const matchingMessages = async () => (await sandboxEmailSubjects(request, recipient))
    .filter((subject) => subject === expectedSubject).length;
  const before = await matchingMessages();

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
  const preview = page.getByRole("region", { name: "Approved message preview" });
  await expect(preview.getByText(recipient, { exact: true })).toBeVisible();
  const execution = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/execute") && response.ok(),
  );
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Execute" }).click();
  const executionBody = await execution.then((response) => response.json() as Promise<{ status: string }>);
  expect(executionBody.status).toBe("executing");

  await page.getByRole("link", { name: "Workflows" }).click();
  await page.getByText("Built-in automation activity", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Email activity" })).toBeVisible();
  const delivery = page.getByRole("region", { name: "Email activity" }).locator(`[data-approval-id="${responseApproval?.id}"]`);
  const accepted = delivery.getByText("Accepted by SMTP", { exact: true });
  await expect(accepted).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Mailpit sandbox")).toBeVisible();

  await expect.poll(
    matchingMessages,
    { timeout: 10_000, intervals: [250, 500, 1_000] },
  ).toBe(before + 1);

  await page.reload();
  await page.getByText("Built-in automation activity", { exact: true }).click();
  await expect(accepted).toBeVisible();
});
