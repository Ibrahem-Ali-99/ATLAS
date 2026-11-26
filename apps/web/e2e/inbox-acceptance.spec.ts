import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { expect, test as base } from "@playwright/test";
import { signInAsSeedAdmin, signInAsSeedStaff } from "./auth";

const test = base.extend<{ storefront: { url: URL; setEmbed: (html: string) => void } }>({
  storefront: async ({ baseURL }, provide) => {
    let embed = "";
    const server = createServer((_req, res) => {
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(`<!doctype html><html lang="en"><title>Delivery desk</title><body>${embed}</body></html>`);
    });
    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", resolve);
    });
    const { port } = server.address() as AddressInfo;
    const url = new URL("/storefront", baseURL);
    url.port = String(port);
    try {
      await provide({ url, setEmbed: (html) => { embed = html; } });
    } finally {
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  },
});

test("website chat settings persist and staff can reply to a visitor on mobile", async ({ page, browser, storefront }) => {
  const visitorMessage = "I need to speak with a human about a delivery.";
  const staffMessage = "Our team can help you with that delivery.";
  await signInAsSeedAdmin(page);
  await page.goto("/inbox");
  await page.getByRole("button", { name: "Website chat settings" }).click();
  const dialog = page.getByRole("dialog", { name: "Website chat settings" });
  await dialog.getByLabel("Allowed website origins").fill(storefront.url.origin);
  await dialog.getByLabel("Welcome message").fill("Welcome to the delivery desk.");
  await dialog.getByLabel("Operating mode").selectOption("human_review");
  const savedConfig = page.waitForResponse((response) =>
    response.request().method() === "PUT" && new URL(response.url()).pathname.endsWith("/inbox/widget"),
  );
  await dialog.getByRole("button", { name: "Save website chat settings" }).click();
  expect((await savedConfig).ok()).toBe(true);
  await expect(dialog.getByRole("status")).toHaveText("Website chat settings saved.");
  await dialog.getByRole("button", { name: "Close" }).click();
  await page.reload();
  await page.getByRole("button", { name: "Website chat settings" }).click();
  await expect(dialog.getByLabel("Allowed website origins")).toHaveValue(storefront.url.origin);
  await expect(dialog.getByLabel("Welcome message")).toHaveValue("Welcome to the delivery desk.");
  storefront.setEmbed(await dialog.getByLabel("Website embed code").inputValue());

  const visitor = await browser.newContext();
  const staff = await browser.newContext({ viewport: { width: 390, height: 844 } });
  try {
    const storefrontPage = await visitor.newPage();
    await storefrontPage.goto(storefront.url.href);
    const launcher = storefrontPage.getByRole("button", { name: "Customer chat" });
    await expect(launcher).toBeVisible();
    await launcher.click();
    const visitorLog = storefrontPage.getByRole("log", { name: "Chat messages" });
    await expect(visitorLog).toContainText("Welcome to the delivery desk.");
    await storefrontPage.getByRole("textbox", { name: "Chat message" }).fill(visitorMessage);
    await storefrontPage.getByRole("button", { name: "Send", exact: true }).click();
    await expect(visitorLog.getByText(`You: ${visitorMessage}`, { exact: true })).toHaveCount(1);

    const agent = await staff.newPage();
    await signInAsSeedStaff(agent);
    await agent.goto("/inbox");
    await expect(agent.getByRole("button", { name: "Website chat settings" })).toHaveCount(0);
    await agent.getByRole("button", { name: /Website chat.*Handoff requested/ }).click();
    await expect(agent.getByRole("log", { name: "Customer messages" }).getByText(visitorMessage, { exact: true })).toBeVisible();
    await agent.getByRole("button", { name: "Show customer context" }).click();
    const context = agent.getByRole("dialog", { name: "Customer context" });
    await expect(context.getByLabel("Conversation assignee")).toBeEnabled();
    await context.getByRole("button", { name: "Accept handoff" }).click();
    await expect(context.getByLabel("Conversation assignee")).not.toHaveValue("");
    await context.getByRole("button", { name: "Close" }).click();
    await agent.getByRole("textbox", { name: "Staff reply" }).fill(staffMessage);
    await agent.getByRole("button", { name: "Send to visitor" }).click();
    await expect(agent.getByRole("log", { name: "Customer messages" }).getByText(staffMessage, { exact: true })).toBeVisible();
    await expect(visitorLog.getByText(staffMessage, { exact: false })).toHaveCount(1);
    await expect(visitorLog.getByText(`You: ${visitorMessage}`, { exact: true })).toHaveCount(1);
    await agent.getByRole("button", { name: "Show customer context" }).click();
    await context.getByLabel("New contact name").fill("Delivery customer");
    await context.getByLabel("New contact email").fill(`delivery-${Date.now()}@example.com`);
    await context.getByRole("button", { name: "Create contact" }).click();
    await context.getByText("Record customer inquiry", { exact: true }).click();
    await context.getByLabel("Lead title").fill("Delivery follow-up");
    await context.getByRole("button", { name: "Create lead and inquiry" }).click();
    await expect(context.getByRole("link", { name: "Open CRM inquiry" })).toBeVisible();
    const leadPath = await context.getByRole("link", { name: "Delivery follow-up" }).getAttribute("href");
    expect(leadPath).toContain("tab=leads");
    const crm = await staff.newPage();
    await crm.goto(leadPath!);
    await crm.getByRole("button", { name: "Request appointment" }).click();
    const appointment = crm.getByRole("dialog", { name: "Request an appointment" });
    const start = new Date(Date.now() + 72 * 3600_000);
    const end = new Date(start.getTime() + 3600_000);
    const local = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
    await appointment.getByLabel("Starts at").fill(local(start));
    await appointment.getByLabel("Ends at").fill(local(end));
    await appointment.getByRole("button", { name: "Check availability" }).click();
    await expect(appointment.getByRole("status")).toHaveText("Available on the ATLAS workspace calendar.");
    await appointment.getByRole("button", { name: "Request approval" }).click();
    await appointment.getByRole("link", { name: "Open approval" }).click();
    const approvalDetails = crm.getByRole("region", { name: "Approval details" });
    await expect(approvalDetails.getByText("Starts at", { exact: true })).toBeVisible();
    await expect(approvalDetails.getByText("ATLAS reservation", { exact: true })).toBeVisible();
    await context.getByRole("button", { name: "Close" }).click();
    expect(await agent.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await page.goto("/integrations");
    await page.getByRole("button", { name: "Website chat settings" }).click();
    await dialog.getByRole("checkbox", { name: /Accept website chats/ }).uncheck();
    await dialog.getByRole("button", { name: "Save website chat settings" }).click();
    await expect(dialog.getByRole("status")).toHaveText("Website chat paused.");
    await storefrontPage.getByRole("textbox", { name: "Chat message" }).fill("This message must remain unsent.");
    const blocked = storefrontPage.waitForResponse((response) => response.request().method() === "POST" && response.url().includes("/widget/"));
    await storefrontPage.getByRole("button", { name: "Send", exact: true }).click();
    expect((await blocked).status()).toBe(404);
    await expect(agent.getByRole("log", { name: "Customer messages" }).getByText(staffMessage, { exact: true })).toBeVisible();
  } finally {
    await visitor.close();
    await staff.close();
  }
});
