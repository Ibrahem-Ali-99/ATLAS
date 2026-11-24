import { expect, test } from "@playwright/test";

test("Knowledge upload, indexing, search, inspection, and removal", async ({ page }) => {
  const stamp = Date.now().toString();
  const title = `Knowledge acceptance ${stamp}`;
  const token = `warehouse-policy-${stamp}`;

  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("change-me-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Operations overview" })).toBeVisible();

  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: "Company knowledge" })).toBeVisible();
  await page.getByLabel("Document origin").selectOption("demo");
  await page.locator('input[type="file"]').setInputFiles({
    name: `${title}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`DEMO KNOWLEDGE FIXTURE. The warehouse reference is ${token}.`),
  });

  const row = page.getByRole("row", { name: title });
  await expect(row).toBeVisible();
  await expect(row.getByRole("cell", { name: "Demo" })).toBeVisible();
  await expect(row.getByRole("cell", { name: "ready" })).toBeVisible({ timeout: 30_000 });

  await row.getByRole("button", { name: title }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText(`DEMO KNOWLEDGE FIXTURE. The warehouse reference is ${token}.`)).toBeVisible();

  await page.getByLabel("Search documents").fill("");
  await page.getByLabel("Search documents").fill(token);
  await page.getByLabel("Search documents").fill("");
  await page.getByLabel("Search documents").fill(token);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(`DEMO KNOWLEDGE FIXTURE. The warehouse reference is ${token}.`)).toBeVisible();

  await row.getByRole("button", { name: "Delete" }).click();
  await page.getByRole("button", { name: "Confirm delete" }).click();
  await expect(page.getByRole("row", { name: title })).toHaveCount(0);

  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(new RegExp(`No indexed excerpts matched.*${token}`))).toBeVisible();
  await page.goto("/assistant");
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await page.getByPlaceholder("Ask about records, documents or your organization…").fill(token);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("I could not find relevant company documents or CRM records for that question.")).toBeVisible();
  await expect(page.getByText(title)).toHaveCount(0);
  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: "Company knowledge" })).toBeVisible();
  await page.screenshot({ path: `../../var/knowledge-browser-acceptance-${stamp}-desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Company knowledge" })).toBeVisible();
  await page.screenshot({ path: `../../var/knowledge-browser-acceptance-${stamp}-mobile.png`, fullPage: true });
});
