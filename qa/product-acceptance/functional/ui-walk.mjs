import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const require = createRequire(path.join(repoRoot, "apps/web/package.json"));
const { chromium } = require("@playwright/test");

const sessionPath = process.argv[2];
const session = JSON.parse(readFileSync(sessionPath, "utf8"));
const evidence = session.evidence;
const shots = path.join(evidence, "screenshots");
mkdirSync(shots, { recursive: true });

const routes = [
  ["/overview", "Overview"],
  ["/crm", "CRM"],
  ["/inbox", "Inbox"],
  ["/assistant", "AI Assistant"],
  ["/knowledge", "Knowledge"],
  ["/approvals", "Approvals"],
  ["/workflows", "Workflows"],
  ["/agent-runs", "Agent Runs"],
  ["/analytics", "Analytics"],
  ["/campaigns", "Campaigns"],
  ["/monitoring", "Monitoring"],
  ["/integrations", "Integrations"],
  ["/billing", "Billing"],
  ["/settings", "Settings"],
];

const findings = [];
const passed = [];
const consoleErrors = [];

function finding(id, severity, module, workstream, title, steps, expected, actual, acceptance) {
  findings.push({ id, severity, module, workstream, title, steps, expected, actual, evidence: "", acceptance });
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
const page = await context.newPage();
page.on("pageerror", (error) => consoleErrors.push(String(error).slice(0, 300)));
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text().slice(0, 300));
});

try {
  await page.goto(`${session.web}/login`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Email").fill(session.adminEmail);
  await page.getByLabel("Password").fill(session.adminPassword);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL(/\/overview(?:\?|$)/, { timeout: 30000 });
  await page.getByLabel("Organization").selectOption({ label: "Atlas Demo" });
  passed.push("sign-in");

  const measurements = await page.evaluate(() => {
    const body = getComputedStyle(document.body);
    const aside = document.querySelector("aside");
    return {
      fontFamily: body.fontFamily,
      fontSize: body.fontSize,
      background: body.backgroundColor,
      sidebarWidth: aside ? Math.round(aside.getBoundingClientRect().width) : null,
    };
  });
  if (!/inter/i.test(measurements.fontFamily)) {
    finding(
      "QA-VIS-TYPE",
      "major",
      "Overview",
      "Workspace interface",
      "The workspace does not use the reference Inter typeface",
      ["Open Overview at 1440×960.", "Read the computed body font."],
      "The reference archive sets Inter as the product typeface.",
      `Computed font: ${measurements.fontFamily}.`,
      "The signed-in workspace uses Inter at the reference size and weight.",
    );
  } else {
    passed.push("typography");
  }

  await page.getByRole("button", { name: "Search workspace" }).click();
  await page.getByLabel("Find a page").fill("Quayline");
  await page.waitForFunction(() => {
    const dialog = document.querySelector("[role=dialog]");
    const text = dialog?.textContent || "";
    return /quayline/i.test(text) || /no matching/i.test(text);
  }, null, { timeout: 8000 }).catch(() => {});
  const searchText = await page.locator("[role=dialog]").innerText();
  await page.keyboard.press("Escape");
  if (/No matching pages/i.test(searchText)) {
    finding(
      "QA-SEARCH-RECORDS",
      "major",
      "Overview",
      "Workspace interface",
      "The primary workspace search does not find saved customers",
      ["Create a company.", "Choose Search workspace.", "Type the company name."],
      "Search opens the company, or the control is named as page navigation rather than workspace search.",
      "The control is labeled Search workspace. A saved company returns: No matching pages.",
      "A workspace search for a saved company name opens that company, or the control's name matches a page-only search.",
    );
  } else if (!/Quayline/i.test(searchText)) {
    finding(
      "QA-SEARCH-RECORDS",
      "major",
      "Overview",
      "Workspace interface",
      "Workspace search does not show the saved company",
      ["Create a company.", "Choose Search workspace.", "Type the company name."],
      "The company is listed.",
      searchText.slice(0, 400),
      "Searching a saved company name shows that company.",
    );
  } else {
    passed.push("workspace-search");
  }

  try {
    await page.getByRole("button", { name: "New opportunity" }).click();
    const create = page.getByRole("button", { name: "Create opportunity" });
    await page.getByRole("textbox", { name: "Opportunity name" }).fill("QA night-gate opportunity");
    if (await create.isDisabled()) {
      finding(
        "QA-OPP-DISABLED",
        "major",
        "Overview",
        "CRM and customer operations",
        "New opportunity cannot be saved",
        ["Open Overview.", "Choose New opportunity.", "Enter a name."],
        "Create opportunity is available and the record appears on the pipeline.",
        "Create opportunity stayed disabled after a name was entered.",
        "An administrator can create an opportunity from Overview and find it in the pipeline.",
      );
      await page.keyboard.press("Escape");
    } else {
      await create.click();
      await page.getByRole("status").filter({ hasText: "Opportunity created" }).waitFor({ timeout: 20000 });
      await page.goto(`${session.web}/crm?tab=opportunities`);
      await page.getByText("QA night-gate opportunity").first().waitFor({ timeout: 20000 });
      passed.push("opportunity-persist");
    }
  } catch (error) {
    finding(
      "QA-OPP-CREATE",
      "major",
      "Overview",
      "CRM and customer operations",
      "Creating an opportunity from Overview does not finish",
      ["Open Overview.", "Choose New opportunity.", "Enter a name and create it.", "Open the pipeline."],
      "The opportunity is visible in the pipeline.",
      String(error).slice(0, 500),
      "An opportunity created from Overview is visible in CRM after navigation.",
    );
  }

  try {
    await page.goto(`${session.web}/crm?tab=companies`);
    await page.getByLabel("Search companies").fill("Quayline");
    await page.getByText("Quayline Cold Storage").first().waitFor({ timeout: 20000 });
    passed.push("crm-ui-search");
  } catch (error) {
    finding(
      "QA-CRM-UI-SEARCH",
      "major",
      "CRM",
      "CRM and customer operations",
      "The companies screen does not show a company saved through the API",
      ["Save a company.", "Open CRM companies.", "Search for its name."],
      "The company is visible.",
      String(error).slice(0, 500),
      "A company saved in this workspace is visible in CRM search.",
    );
  }

  for (const [href, label] of routes) {
    await page.goto(`${session.web}${href}`, { waitUntil: "domcontentloaded" });
    await page.getByRole("main").waitFor({ timeout: 20000 });
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => undefined);
    const file = path.join(shots, `${label.toLowerCase().replaceAll(" ", "-")}-1440.png`);
    await page.screenshot({ path: file });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    if (overflow) {
      finding(
        `QA-VIS-OVERFLOW-${label.toUpperCase().replaceAll(" ", "-")}`,
        "major",
        label,
        "Workspace interface",
        `${label} overflows horizontally at 1440px`,
        [`Open ${label} at 1440×960.`],
        "The page fits the viewport.",
        "The document is wider than the viewport.",
        `${label} has no horizontal overflow at 1440px.`,
      );
    }
    const failed = page.getByRole("alert");
    if (await failed.count() && /failed|unreachable|unavailable/i.test(await failed.first().innerText())) {
      finding(
        `QA-UI-ALERT-${label.toUpperCase().replaceAll(" ", "-")}`,
        "major",
        label,
        "Workspace interface",
        `${label} shows an error after a successful sign-in`,
        [`Sign in.`, `Open ${label}.`],
        "The module renders its records or an honest empty state.",
        (await failed.first().innerText()).slice(0, 300),
        `${label} loads without a request failure for the seeded administrator.`,
      );
    } else {
      passed.push(`route-${label}`);
    }
  }

  const billingText = await page.goto(`${session.web}/billing`).then(() => page.getByRole("main").innerText());
  if (/live charge|payment succeeded|subscribed/i.test(billingText)) {
    finding(
      "QA-BILL-COPY",
      "blocker",
      "Billing",
      "Billing and settings",
      "Billing implies a completed live charge",
      ["Open Billing on the sandbox acceptance process. Do not start checkout."],
      "The page identifies sandbox or test billing and does not claim a charge.",
      billingText.slice(0, 400),
      "Billing copy matches the sandbox provider and does not report a charge that was not made.",
    );
  }

  const integrationsText = await page.goto(`${session.web}/integrations`).then(async () => {
    await page.getByRole("main").waitFor();
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => undefined);
    return page.getByRole("main").innerText();
  });
  writeFileSync(path.join(evidence, "integrations-visible.txt"), integrationsText, "utf8");

  await page.goto(`${session.web}/campaigns`);
  await page.getByRole("main").waitFor();
  const campaignText = await page.getByRole("main").innerText();
  if (/QA night gate draft/.test(campaignText) && /Night gate hours/.test(campaignText) && /Add a subject, message/.test(campaignText)) {
    finding(
      "QA-CAMP-GUIDANCE",
      "major",
      "Campaigns",
      "Campaigns and communications",
      "A saved campaign draft still tells the operator to add a subject and message",
      ["Save a campaign draft with a subject and a message.", "Open the draft.", "Read the delivery guidance and the Schedule delivery control."],
      "The guidance names only the missing requirement, such as an eligible audience.",
      "The draft shows its subject and message, and the delivery text still says to add a subject, message, and eligible recipients.",
      "Delivery guidance matches the draft that is already saved.",
    );
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${session.web}/overview`);
  await page.getByRole("main").waitFor();
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  await page.screenshot({ path: path.join(shots, "overview-390.png") });
  if (mobileOverflow) {
    finding(
      "QA-VIS-MOBILE",
      "major",
      "Overview",
      "Workspace interface",
      "Overview overflows on a 390px-wide screen",
      ["Open Overview at 390×844."],
      "The page fits the width.",
      "The document is wider than the viewport.",
      "Overview has no horizontal overflow at 390px.",
    );
  } else {
    passed.push("mobile-overview");
  }

  writeFileSync(path.join(evidence, "visual-measurements.json"), JSON.stringify({ measurements, consoleErrors }, null, 2));
} catch (error) {
  finding(
    "QA-UI-WALK",
    "blocker",
    "Overview",
    "Workspace interface",
    "The signed-in product walk could not be completed",
    ["Start the isolated acceptance web app.", "Sign in as the seeded administrator.", "Visit every workspace module."],
    "Every module opens and the covered controls respond.",
    String(error).slice(0, 800),
    "The browser walk completes against the isolated workspace.",
  );
} finally {
  await browser.close();
}

writeFileSync(path.join(evidence, "ui-walk.json"), JSON.stringify({ findings, passed, consoleErrors }, null, 2));
console.log(`QA_UI findings=${findings.length} passed=${passed.length}`);
