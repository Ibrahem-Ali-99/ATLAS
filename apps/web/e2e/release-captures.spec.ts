import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const portfolio = path.resolve(process.cwd(), "public/portfolio");

test.use({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  colorScheme: "light",
});

test("capture 1440×900 Harbor product frames", async ({ page }) => {
  test.skip(process.env.ATLAS_RELEASE_CAPTURES !== "1", "Set ATLAS_RELEASE_CAPTURES=1 to replace website product frames");
  test.setTimeout(180_000);
  await page.addInitScript(() => window.localStorage.setItem("atlas.theme", "light"));
  await page.goto("/demo");
  const launch = page.getByRole("main").getByRole("button", { name: "Launch interactive demo" }).first();
  await expect(launch).toBeEnabled({ timeout: 30_000 });
  await launch.click();
  await page.waitForURL(/\/overview/);
  await expect(page.getByTestId("overview-kpi-companies-value")).toHaveText("20", { timeout: 60_000 });
  await frame(page, "01-overview.png");

  await page.getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page.getByRole("button", { name: "Harbor & Co.", exact: true })).toBeVisible();
  await frame(page, "02-crm.png");

  await page.getByRole("link", { name: "Inbox", exact: true }).click();
  await page.getByLabel("Search inbox").fill("Cold storage");
  await page.getByRole("button", { name: /Cold storage for the north pier/ }).click();
  await expect(page.getByText("Could you confirm bonded and cold storage at the north pier yard?")).toBeVisible();
  await frame(page, "14-inbox.png");

  await page.getByRole("link", { name: "Knowledge", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Company knowledge" })).toBeVisible();
  await expect(page.getByText("Bonded warehousing overview")).toBeVisible();
  await frame(page, "03-knowledge.png");

  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByLabel("Search workflows").fill("Qualified lead");
  await page.getByRole("button", { name: /Qualified lead follow-up/ }).click();
  await expect(page.getByRole("heading", { name: "Qualified lead follow-up" })).toBeVisible();
  await page.getByLabel("Search workflows").fill("");
  await expect(page.getByRole("button", { name: /New lead intake/ })).toBeVisible();
  await frame(page, "07-workflows.png");

  await page.getByRole("link", { name: "Analytics", exact: true }).click();
  await page.getByLabel("Analytics date range").selectOption("90d");
  await expect(page.getByTestId("analytics-metric-active-companies-value")).toHaveText("20");
  await expect(page.getByTestId("analytics-metric-leads-value")).toHaveText("50");
  await frame(page, "08-analytics.png");

  await page.getByRole("link", { name: "Integrations", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Email", exact: true })).toBeVisible();
  await frame(page, "15-integrations.png");

  await page.setViewportSize({ width: 390, height: 844 });
  const overflows: string[] = [];
  for (const route of ["overview", "crm", "inbox", "knowledge", "workflows", "analytics", "integrations"]) {
    await page.goto(`/${route}`);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    if (width > 391) {
      const culprit = await page.evaluate(() => {
        let worst = "";
        let max = 0;
        for (const node of document.querySelectorAll("body *")) {
          const rect = node.getBoundingClientRect();
          if (rect.width > max) {
            max = rect.width;
            const label = node.className && typeof node.className === "string" ? node.className : "";
            worst = `${node.tagName} ${label.slice(0, 90)} ${Math.round(rect.width)}`;
          }
        }
        return worst;
      });
      overflows.push(`${route} ${width} :: ${culprit}`);
    }
  }
  expect(overflows).toEqual([]);

  const homeDir = path.resolve(process.cwd(), "../../var/release-home");
  mkdirSync(homeDir, { recursive: true });
  for (const [width, height] of [[1440, 900], [390, 844]] as const) {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const homeWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(homeWidth, `home ${width}`).toBeLessThanOrEqual(width + 1);
    await page.screenshot({
      path: path.join(homeDir, `home-${width}.png`),
      animations: "disabled",
    });
    await page.locator("#crm").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(homeDir, `home-crm-${width}.png`),
      animations: "disabled",
    });
    await page.locator("#integrations").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(homeDir, `home-integrations-${width}.png`),
      animations: "disabled",
    });
    await page.goto("/demo");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const demoWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(demoWidth, `demo ${width}`).toBeLessThanOrEqual(width + 1);
    await page.screenshot({
      path: path.join(homeDir, `demo-${width}.png`),
      animations: "disabled",
    });
  }
});

async function frame(page: Page, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: path.join(portfolio, name),
    animations: "disabled",
    fullPage: false,
  });
}
