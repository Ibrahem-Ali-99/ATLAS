import { expect, test, type Page } from "@playwright/test";

const admin = { email: "admin@example.com", password: "change-me-admin" };
const modules: Array<[string, string | RegExp]> = [
  ["Overview", /Good morning/],
  ["CRM", "Companies"],
  ["Inbox", "Inbox"],
  ["Assistant", "New conversation"],
  ["Knowledge", "Knowledge"],
  ["Approvals", "Approvals"],
  ["Workflows", "Workflows"],
  ["Agent Runs", "Agent Runs"],
  ["Analytics", "Analytics"],
  ["Campaigns", "Campaigns"],
  ["Monitoring", "Monitoring"],
  ["Integrations", "Integrations"],
  ["Billing", "Billing"],
  ["Settings", "Settings"],
];

let companyName = "";

async function signIn(page: Page): Promise<void> {
  const login = page.waitForResponse((response) => response.url().includes("/api/v1/auth/login"));
  await page.goto("/login");
  await page.getByLabel("Email address").fill(admin.email);
  await page.getByLabel("Password").fill(admin.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const response = await login;
  expect(response.ok(), `login status ${response.status()}`).toBe(true);
  await expect(page.getByRole("heading", { level: 1, name: /Good morning/ })).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("a wrong password stays on the sign-in screen", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(admin.email);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});

test("the seeded administrator signs in with an HttpOnly session", async ({ page }) => {
  await signIn(page);
  const session = (await page.context().cookies()).find((cookie) => cookie.name === "atlas_session");
  expect(session?.httpOnly).toBe(true);
  const visible = await page.evaluate(() => document.cookie);
  expect(visible).not.toContain("atlas_session");
});

test("every workspace module opens", async ({ page }) => {
  await signIn(page);
  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  for (const [label, heading] of modules) {
    await navigation.getByRole("button", { name: label }).click();
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  }
});

test("a company created in CRM stays in this organization", async ({ page }) => {
  companyName = `Gate Company ${Date.now()}`;
  await signIn(page);
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "CRM" }).click();
  await page.getByRole("button", { name: "New company" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill(companyName);
  await page.getByRole("button", { name: "Create record" }).click();
  await page.getByLabel("Search companies").fill(companyName);
  await expect(page.getByRole("button", { name: `Open ${companyName}` })).toBeVisible();
});

test("Assistant answers a question in the workspace", async ({ page }) => {
  await signIn(page);
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Assistant" }).click();
  await page.getByLabel("Ask ATLAS Assistant").fill("What companies are in this workspace?");
  const reply = page.waitForResponse(
    (response) => response.url().includes("/messages/stream") && response.ok(),
  );
  await page.getByRole("button", { name: "Send question" }).click();
  await reply;
  await expect(page.getByRole("article", { name: "ATLAS Assistant" }).last()).not.toHaveText("");
});

test("an uploaded note is retrieved by semantic search", async ({ page }) => {
  const token = `HBR-GATE-${Date.now()}`;
  await signIn(page);
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Knowledge" }).click();
  await page.getByRole("button", { name: "Upload document" }).click();
  await page.getByLabel("Choose a knowledge document").setInputFiles({
    name: "gate-note.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(`The quay gate token is ${token}.`),
  });
  await page.getByRole("button", { name: "Upload and index" }).click();
  await expect(page.getByRole("row", { name: /gate-note/ })).toBeVisible();
  await expect(async () => {
    await page.reload();
    await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Knowledge" }).click();
    await expect(page.getByRole("row", { name: /gate-note/ })).toContainText("Indexed");
  }).toPass({ timeout: 90_000 });
  await page.getByRole("button", { name: "Semantic search" }).click();
  await page.getByLabel("Semantic knowledge search").fill(token);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(token)).toBeVisible();
});

test("a workflow approval can be granted", async ({ page }) => {
  const name = `Gate review ${Date.now()}`;
  await signIn(page);
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Workflows" }).click();
  await page.getByRole("button", { name: "New workflow" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Workflow name").fill(name);
  await dialog.locator("select").first().selectOption("Status changed");
  await dialog.getByLabel("Workflow condition").selectOption("new");
  await dialog.getByLabel("Otherwise task").fill("Gate follow-up");
  await dialog.getByRole("button", { name: "Save workflow" }).click();
  await expect(page.getByRole("button", { name })).toBeVisible();
  await page.getByRole("button", { name: "Activate" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await page.getByRole("button", { name: "Test in sandbox" }).click();
  await expect(page.getByRole("heading", { name: "Run workflow" })).toBeVisible();
  await page.getByRole("button", { name: "Run locally" }).click();
  await expect(page.getByRole("heading", { name: "Workflow run details" })).toBeVisible();
  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  await page.getByRole("button", { name: "Close workflow run" }).last().click();
  await expect(async () => {
    await navigation.getByRole("button", { name: "Overview" }).click();
    await navigation.getByRole("button", { name: "Workflows" }).click();
    await page.getByRole("button", { name }).click();
    await page.getByRole("button", { name: "View run" }).click();
    await expect(page.getByRole("button", { name: "Approve internal step" })).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: 20_000 });
  await page.getByRole("button", { name: "Approve internal step" }).click();
  await expect(page.getByText("Internal step approved")).toBeVisible();
});

test("analytics exports the opportunity report", async ({ page }) => {
  await signIn(page);
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Analytics" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export opportunities" }).click();
  expect((await download).suggestedFilename()).toBe("opportunities.csv");
});

test("settings shows the signed-in members", async ({ page }) => {
  await signIn(page);
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name: "Members" }).click();
  await expect(page.getByText(admin.email)).toBeVisible();
});

test("the narrow layout still opens a module", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Billing" }).click();
  await expect(page.getByRole("heading", { name: "Billing" })).toBeVisible();
});

test("a visitor cannot see the administrator company", async ({ page, browser }) => {
  expect(companyName).not.toBe("");
  await signIn(page);
  const visitor = await browser.newContext();
  const visitorPage = await visitor.newPage();
  try {
    await visitorPage.goto("/demo");
    await visitorPage.getByRole("button", { name: "Launch interactive demo" }).click();
    await expect(visitorPage.getByRole("heading", { level: 1, name: /Good morning/ })).toBeVisible({
      timeout: 180_000,
    });
    await expect(visitorPage.getByLabel("Breadcrumb")).toContainText("Harbor & Co.");
    await visitorPage.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "CRM" }).click();
    await visitorPage.getByLabel("Search companies").fill("Sable");
    await expect(visitorPage.getByRole("button", { name: "Open Sable Fisheries" })).toBeVisible();
    await visitorPage.getByLabel("Search companies").fill(companyName);
    await expect(visitorPage.getByRole("button", { name: `Open ${companyName}` })).toHaveCount(0);
  } finally {
    await visitor.close();
  }
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "CRM" }).click();
  await page.getByLabel("Search companies").fill("Sable");
  await expect(page.getByRole("button", { name: "Open Sable Fisheries" })).toHaveCount(0);
  await page.getByRole("button", { name: "Open profile menu" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});
