import { chromium } from "@playwright/test";

const baseURL = process.env.STAGING_BASE_URL;
const email = process.env.SEED_ADMIN_EMAIL;
const password = process.env.SEED_ADMIN_PASSWORD;
const fullName = process.env.SEED_ADMIN_NAME ?? "Staging Admin";
const channel = process.env.STAGING_BROWSER_CHANNEL || "msedge";

if (!baseURL || !email || !password) {
  console.error("STAGING_BASE_URL, SEED_ADMIN_EMAIL, and SEED_ADMIN_PASSWORD are required");
  process.exit(1);
}

const leaked = [];
const browser = await chromium.launch({ channel, headless: true });
const context = await browser.newContext({
  baseURL,
  ignoreHTTPSErrors: false,
  viewport: { width: 1440, height: 900 },
});
const page = await context.newPage();
page.on("request", (request) => {
  const url = request.url();
  if (url.includes("127.0.0.1:8000") || url.includes("localhost:8000")) {
    leaked.push(url);
  }
});

try {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Operations overview" }).waitFor();

  const nav = page.getByRole("navigation", { name: "Workspace" });
  await nav.getByRole("link", { name: "CRM" }).click();
  await page.getByRole("heading", { name: "Customer records" }).waitFor();
  await nav.getByRole("link", { name: "Knowledge" }).click();
  await page.getByRole("heading", { name: "Company knowledge" }).waitFor();
  await nav.getByRole("link", { name: "AI Assistant" }).click();
  await page.getByRole("heading", { name: "Assistant" }).waitFor();
  await nav.getByRole("link", { name: "Overview" }).click();
  await page.getByRole("heading", { name: "Operations overview" }).waitFor();

  await page.getByRole("button", { name: new RegExp(fullName) }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("heading", { name: "Sign in" }).waitFor();

  await page.goto("/overview");
  await page.getByRole("heading", { name: "Sign in" }).waitFor();

  if (leaked.length > 0) {
    throw new Error(`The browser called the loopback API: ${leaked.join(", ")}`);
  }
  console.log("browser_ok", channel, baseURL);
} finally {
  await browser.close();
}
