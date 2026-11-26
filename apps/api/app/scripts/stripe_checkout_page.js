const { chromium } = require("@playwright/test");

const url = process.env.ATLAS_CHECKOUT_URL || "";
if (!url.startsWith("https://checkout.stripe.com/")) {
  console.error("checkout_url_missing");
  process.exit(1);
}

async function fillAnyFrame(page, autocomplete, value) {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    for (const frame of page.frames()) {
      const input = frame.locator(`input[autocomplete="${autocomplete}"]`);
      if (await input.count()) {
        await input.first().fill(value);
        return;
      }
    }
    await page.waitForTimeout(250);
  }
  throw new Error(`missing_${autocomplete}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    const root = page.frameLocator('iframe[title="Secure embedded form frame"]');
    const email = root.locator("input[name='email']");
    await email.waitFor({ state: "visible", timeout: 20000 });
    await email.fill("harbor-provider-check@harbor.example");
    await root.getByText("Card", { exact: true }).click({ timeout: 10000 });
    await fillAnyFrame(page, "cc-number", "4242424242424242");
    await fillAnyFrame(page, "cc-exp", "1234");
    await fillAnyFrame(page, "cc-csc", "123");
    const name = root.getByPlaceholder("First and last name");
    if (await name.count()) {
      await name.fill("Harbor Provider Check");
    }
    const country = root.locator("select[name='billingCountry']");
    if (await country.count()) {
      await country.first().selectOption("US");
    }
    const postal = root.locator("input[name='billingPostalCode']");
    if (await postal.count()) {
      await postal.first().fill("10001");
    }
    await root.getByRole("button", { name: "Subscribe" }).click();
    await page.waitForURL(/checkout=(success|canceled)|billing/i, { timeout: 30000 });
    if (page.url().includes("checkout=canceled")) {
      console.error("checkout_canceled");
      process.exit(1);
    }
    console.log("checkout_submitted");
  } catch (error) {
    const message = error instanceof Error ? error.message : "checkout_failed";
    console.error(`error=${message.split("\n")[0].slice(0, 180)}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
