import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { signInAsSeedAdmin } from "./auth";

test("an activated workflow creates a task from a new lead", async ({ page }) => {
  const stamp = Date.now();
  const workflow = `New customer review ${stamp}`;
  const taskTitle = `Review customer request ${stamp}`;
  const lead = `Workflow lead ${stamp}`;
  await signInAsSeedAdmin(page);
  await page.goto("/workflows");
  const builder = page.getByRole("region", { name: "Workflow builder" });
  await builder.getByRole("button", { name: "New workflow" }).click();
  const editor = page.getByRole("dialog", { name: "New workflow" });
  await editor.getByLabel("Workflow name").fill(workflow);
  await editor.getByLabel("Trigger").selectOption("lead_created");
  await editor.getByLabel("Task title").fill(taskTitle);
  await editor.getByRole("button", { name: "Create draft" }).click();
  await expect(editor).toBeHidden();
  const details = builder.getByRole("region", { name: "Workflow details" });
  await expect(details.getByRole("heading", { name: workflow })).toBeVisible();
  await expect(details.getByText(taskTitle)).toBeVisible();
  await details.getByRole("button", { name: "Activate" }).click();
  await expect(details.getByRole("button", { name: "Pause" })).toBeVisible();

  await page.goto("/crm?tab=leads");
  await page.getByRole("button", { name: "New lead" }).click();
  const leadEditor = page.getByRole("dialog", { name: "New lead" });
  await leadEditor.getByLabel("Title").fill(lead);
  await leadEditor.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("heading", { name: lead, exact: true })).toBeVisible();

  await page.goto("/workflows");
  const tasks = page.getByRole("region", { name: "Workflow tasks" });
  const taskStatus = tasks.getByLabel(`Task status for ${taskTitle}`);
  await expect(taskStatus).toHaveValue("open");
  await taskStatus.selectOption("completed");
  await expect(taskStatus).toHaveValue("completed");
  await page.reload();
  await expect(taskStatus).toHaveValue("completed");

  await builder.getByLabel("Search workflows").fill(workflow);
  await details.getByRole("button", { name: "Pause" }).click();
  await expect(details.getByRole("button", { name: "Activate" })).toBeVisible();
});

test("a manual test follows the canvas approval gate and leaves inspectable history", async ({ page }) => {
  const name = `Approved actions ${Date.now()}`;
  await signInAsSeedAdmin(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workflows");
  await page.getByRole("button", { name: "New workflow" }).click();
  const editor = page.getByRole("dialog", { name: "New workflow" });
  await editor.getByLabel("Workflow name").fill(name);
  await editor.getByLabel("Trigger").selectOption("manual");
  await editor.getByLabel("Task title").fill(name);
  await editor.getByRole("button", { name: "Create draft" }).click();
  const details = page.getByRole("region", { name: "Workflow details" });
  await details.getByRole("button", { name: "Add approval" }).click();
  await details.getByLabel("Reviewer instructions").fill("Confirm the task is ready.");
  const evidence = process.env.ATLAS_E2E_ARTIFACT_DIR;
  if (evidence) {
    mkdirSync(evidence, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.screenshot({ path: path.join(evidence, "workflow-builder-desktop.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    await details.getByRole("heading", { name: "Node configuration" }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(evidence, "workflow-builder-mobile.png") });
  }
  await details.getByRole("button", { name: "Validate" }).click();
  await expect(details.getByText("Workflow validated.")).toBeVisible();
  await details.getByRole("button", { name: "Save changes" }).click();
  await expect(details.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await details.getByRole("button", { name: "Runs and approvals" }).click();
  await details.getByRole("button", { name: "Test workflow" }).click();
  await page.getByRole("dialog", { name: "Test workflow" }).getByRole("button", { name: "Run on this record" }).click();
  const run = details.getByRole("region", { name: "Run inspection" });
  await expect(run.getByText("Confirm the task is ready.")).toBeVisible();
  await page.goto("/approvals");
  await page.getByRole("complementary", { name: "Pending workflow approvals" }).getByRole("link", { name: new RegExp(name) }).click();
  await expect(run.getByText("Confirm the task is ready.")).toBeVisible();
  const tasks = page.getByRole("region", { name: "Workflow tasks" });
  await expect(tasks.getByText(name, { exact: true })).toHaveCount(0);
  await run.getByRole("button", { name: "Approve", exact: true }).click();
  await run.getByRole("button", { name: "Confirm approval" }).click();
  await expect(run.getByText("Completed", { exact: true })).not.toHaveCount(0);
  await expect(tasks.getByText(name, { exact: true })).toBeVisible();
  await details.getByRole("button", { name: "Canvas" }).click();
  await details.getByText("Workflow settings", { exact: true }).click();
  await details.getByRole("button", { name: "Archive workflow" }).click();
  await details.getByRole("button", { name: "Confirm archive" }).click();
  await page.getByRole("button", { name: "Archived", exact: true }).click();
  await expect(details.getByRole("heading", { name })).toBeVisible();
  await details.getByRole("button", { name: "Runs and approvals" }).click();
  await expect(run.getByText("Run details")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test("the workflow canvas persists alternate paths and step order", async ({ page }) => {
  const name = `Branch workflow ${Date.now()}`;
  await signInAsSeedAdmin(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workflows");
  await page.getByRole("button", { name: "New workflow" }).click();
  const editor = page.getByRole("dialog", { name: "New workflow" });
  await editor.getByLabel("Workflow name").fill(name);
  await editor.getByLabel("Trigger").selectOption("lead_created");
  await editor.getByLabel("Task title").fill("Review matched lead");
  await editor.getByRole("button", { name: "Create draft" }).click();
  const details = page.getByRole("region", { name: "Workflow details" });
  await details.getByRole("button", { name: "Add condition" }).click();
  await details.getByLabel("Match conditions").selectOption("any");
  await details.getByLabel("Lead status").selectOption("qualified");
  await details.getByRole("button", { name: "Add otherwise action" }).click();
  await details.getByLabel("Task title").fill("Review another lead");
  await details.getByRole("button", { name: "Add otherwise action" }).click();
  await details.getByLabel("Task title").fill("Notify account owner");
  await details.getByLabel("Task priority").selectOption("high");
  await details.getByLabel("Due after execution (hours)").fill("24");
  await details.getByRole("button", { name: "Move action up" }).click();
  await details.getByRole("button", { name: "Save changes" }).click();
  await expect(details.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await page.reload();
  await page.getByRole("button", { name: new RegExp(name) }).click();
  const otherwise = details.getByRole("region", { name: "Otherwise", exact: true });
  await expect(otherwise.getByRole("button")).toHaveText([
    /Notify account owner/, /Review another lead/,
  ]);
  await otherwise.getByRole("button", { name: /Notify account owner/ }).click();
  await expect(details.getByLabel("Task priority")).toHaveValue("high");
  await expect(details.getByLabel("Due after execution (hours)")).toHaveValue("24");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});
